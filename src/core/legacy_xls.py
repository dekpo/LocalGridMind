"""Read older Excel (.xls / BIFF). Convert via Excel when possible."""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

XLS_FORMULA_NOTICE = (
    "Stored formulas could not be read from this older Excel format (.xls)."
)
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_CONVERT_DIR_PREFIX = "lgm-xls-"
_XL_OPEN_XML = 51  # Excel FileFormat for .xlsx
_CREATE_NO_WINDOW = 0x08000000
_CONVERT_TIMEOUT_S = 120


def convert_xls_to_temp_xlsx(src: Path) -> Path | None:
    """Save a temp .xlsx through Excel on Windows. Caller must delete it."""
    if sys.platform != "win32":
        return None
    source = Path(src)
    if not source.is_file():
        return None
    tmpdir = Path(tempfile.mkdtemp(prefix=_CONVERT_DIR_PREFIX))
    dest = tmpdir / f"{source.stem}.xlsx"
    try:
        if _convert_with_cscript(source, dest, tmpdir):
            return dest
        if _convert_with_win32com(source, dest):
            return dest
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)
    return None


def cleanup_converted_xlsx(path: Path | None) -> None:
    """Remove a temp workbook produced by `convert_xls_to_temp_xlsx`."""
    if path is None:
        return
    parent = path.parent
    path.unlink(missing_ok=True)
    if parent.name.startswith(_CONVERT_DIR_PREFIX):
        shutil.rmtree(parent, ignore_errors=True)


def xls_has_vba(path: Path) -> bool:
    """Detect-only: OLE `_VBA_PROJECT` marker. Do not interpret macros."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    if not data.startswith(_OLE_MAGIC):
        return False
    return b"_VBA_PROJECT" in data


def iter_xls_value_sheets(path: Path) -> list[tuple[str, list[list[Any]]]]:
    """Sheet name plus cell values. No stored formulas."""
    last_error: Exception | None = None
    for reader in (_sheets_from_xlrd, _sheets_from_calamine, _sheets_from_biff2):
        try:
            return reader(path)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("No .xls value reader is available.")


def _sheets_from_xlrd(path: Path) -> list[tuple[str, list[list[Any]]]]:
    import xlrd

    book = xlrd.open_workbook(str(path), on_demand=True)
    sheets: list[tuple[str, list[list[Any]]]] = []
    try:
        for sheet in book.sheets():
            rows: list[list[Any]] = []
            for row_idx in range(sheet.nrows):
                row: list[Any] = []
                for col_idx in range(sheet.ncols):
                    row.append(_xlrd_value(book, sheet.cell(row_idx, col_idx)))
                rows.append(row)
            sheets.append((sheet.name, rows))
    finally:
        book.release_resources()
    return sheets


def _xlrd_value(book: Any, cell: Any) -> Any:
    import xlrd

    if cell.ctype == xlrd.XL_CELL_EMPTY:
        return None
    if cell.ctype == xlrd.XL_CELL_BLANK:
        return None
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate_as_datetime(cell.value, book.datemode)
        except Exception:
            return cell.value
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return None
    return cell.value


def _sheets_from_calamine(path: Path) -> list[tuple[str, list[list[Any]]]]:
    from python_calamine import CalamineWorkbook

    book = CalamineWorkbook.from_path(str(path))
    sheets: list[tuple[str, list[list[Any]]]] = []
    for name in book.sheet_names:
        data = book.get_sheet_by_name(name).to_python(skip_empty_area=False)
        rows = [list(row) for row in data]
        sheets.append((name, rows))
    return sheets


def _sheets_from_biff2(path: Path) -> list[tuple[str, list[list[Any]]]]:
    """Read a flat Excel 2.0 stream (synthetic tests). Not BIFF8/OLE."""
    data = Path(path).read_bytes()
    if len(data) < 8 or data[0:2] != b"\x09\x00":
        raise ValueError("Not a BIFF2 workbook")
    cells: dict[tuple[int, int], Any] = {}
    max_row = -1
    max_col = -1
    offset = 0
    while offset + 4 <= len(data):
        code, length = struct.unpack_from("<HH", data, offset)
        offset += 4
        payload = data[offset : offset + length]
        offset += length
        if code == 0x000A:
            break
        if code == 0x0004 and len(payload) >= 6:
            row, col = struct.unpack_from("<HH", payload)
            count = payload[5]
            text = payload[6 : 6 + count].decode("latin-1", errors="replace")
            cells[(row, col)] = text
            max_row = max(max_row, row)
            max_col = max(max_col, col)
        elif code == 0x0003 and len(payload) >= 13:
            row, col = struct.unpack_from("<HH", payload)
            value = struct.unpack_from("<d", payload, 5)[0]
            if value.is_integer():
                value = int(value)
            cells[(row, col)] = value
            max_row = max(max_row, row)
            max_col = max(max_col, col)
    if max_row < 0:
        raise ValueError("No BIFF2 cells")
    rows = [
        [cells.get((row, col)) for col in range(max_col + 1)]
        for row in range(max_row + 1)
    ]
    return [("Sheet1", rows)]


def _convert_with_cscript(src: Path, dest: Path, tmpdir: Path) -> bool:
    script = tmpdir / "convert.vbs"
    script.write_text(
        _excel_convert_vbs(src, dest),
        encoding="ascii",
        errors="replace",
    )
    creationflags = _CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(
            ["cscript", "//Nologo", str(script)],
            capture_output=True,
            timeout=_CONVERT_TIMEOUT_S,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        script.unlink(missing_ok=True)
    return completed.returncode == 0 and dest.is_file()


def _convert_with_win32com(src: Path, dest: Path) -> bool:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False
    excel = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.AskToUpdateLinks = False
        book = excel.Workbooks.Open(str(src.resolve()), UpdateLinks=0, ReadOnly=True)
        if dest.exists():
            dest.unlink()
        book.SaveAs(str(dest.resolve()), FileFormat=_XL_OPEN_XML)
        book.Close(False)
        return dest.is_file()
    except Exception:
        return False
    finally:
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass


def _excel_convert_vbs(src: Path, dest: Path) -> str:
    source = _vbs_string(src.resolve())
    target = _vbs_string(dest.resolve())
    return (
        "On Error Resume Next\n"
        "Dim excel, book\n"
        'Set excel = CreateObject("Excel.Application")\n'
        "If Err.Number <> 0 Then WScript.Quit 1\n"
        "excel.Visible = False\n"
        "excel.DisplayAlerts = False\n"
        "excel.AskToUpdateLinks = False\n"
        "excel.AlertBeforeOverwriting = False\n"
        f'Set book = excel.Workbooks.Open("{source}", 0, True)\n'
        "If Err.Number <> 0 Then\n"
        "  excel.Quit\n"
        "  WScript.Quit 1\n"
        "End If\n"
        f'book.SaveAs "{target}", {_XL_OPEN_XML}\n'
        "If Err.Number <> 0 Then\n"
        "  book.Close False\n"
        "  excel.Quit\n"
        "  WScript.Quit 1\n"
        "End If\n"
        "book.Close False\n"
        "excel.Quit\n"
        "WScript.Quit 0\n"
    )


def _vbs_string(path: Path) -> str:
    return str(path).replace('"', '""')
