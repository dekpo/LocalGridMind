"""Compact workbook inventory: schema, stored formulas, links, feature flags."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

ALLOWED_SUFFIXES = {".xlsx", ".xlsm", ".csv"}
MAX_SAMPLE_VALUES = 3
MAX_SAMPLE_CHARS = 24
MAX_FORMULAS_PER_FILE = 40
MAX_FORMULAS_PER_SHEET = 12
MAX_FORMULA_CHARS = 120
MAX_COLUMNS = 40
MAX_SCAN_ROWS = 2000
MAX_SCAN_COLS = 50
MAX_PROMPT_CHARS = 2600
MAX_LABEL_CHARS = 48
EMPTY_COLUMN_RATIO = 0.8
TITLE_ROW_MIN_CHARS = 40
TRIM_MARKER = "… (inventory trimmed)"

_BRACKET_REF = re.compile(r"\[([^\]]+)\]")
_INDEXED_BOOK = re.compile(r"^\d+$")
_SHEET_CELL = re.compile(
    r"(?:'([^']+)'|([A-Za-z0-9._ ]+))!\$?([A-Z]{1,3})\$?(\d+)"
)
_FINANCE_TERMS = (
    "wacc",
    "cost of capital",
    "fcff",
    "fcfe",
    "terminal",
)


@dataclass
class ColumnInfo:
    name: str
    inferred_type: str
    samples: list[str] = field(default_factory=list)
    empty_ratio: float = 0.0
    issues: list[str] = field(default_factory=list)


@dataclass
class SheetInfo:
    name: str
    row_count: int
    column_count: int
    columns: list[ColumnInfo] = field(default_factory=list)
    empty_notes: list[str] = field(default_factory=list)
    hidden: bool = False
    truncated: bool = False


@dataclass
class FormulaInfo:
    cell: str
    formula: str
    external_books: list[str] = field(default_factory=list)
    label: str = ""
    column_header: str = ""


@dataclass
class NamedRangeInfo:
    name: str
    refers_to: str


@dataclass
class ExternalLinkInfo:
    workbook: str
    used_in: str
    present_in_pack: bool = False


@dataclass
class FeatureFlags:
    vba: bool = False
    power_query: bool = False
    pivot: bool = False
    dax: bool = False

    def any(self) -> bool:
        return self.vba or self.power_query or self.pivot or self.dax


@dataclass
class FileInventory:
    filename: str
    kind: str
    sheets: list[SheetInfo] = field(default_factory=list)
    named_ranges: list[NamedRangeInfo] = field(default_factory=list)
    formulas: list[FormulaInfo] = field(default_factory=list)
    links: list[ExternalLinkInfo] = field(default_factory=list)
    features: FeatureFlags = field(default_factory=FeatureFlags)
    issues: list[str] = field(default_factory=list)
    unreadable: bool = False
    formula_total: int = 0


@dataclass
class PackInventory:
    files: list[FileInventory] = field(default_factory=list)
    missing_links: list[str] = field(default_factory=list)

    def filenames(self) -> list[str]:
        return [item.filename for item in self.files]

    def display_name(self) -> str:
        names = self.filenames()
        if not names:
            return "Workbook pack"
        if len(names) == 1:
            return names[0]
        return f"{names[0]} + {len(names) - 1} more"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True)

    def to_english(self) -> str:
        return format_english(self)

    def to_prompt(self, *, budget: int = MAX_PROMPT_CHARS) -> str:
        return format_prompt(self, budget=budget)


def is_workbook_name(name: str) -> bool:
    suffix = Path(str(name).replace("\\", "/")).suffix.lower()
    return suffix in ALLOWED_SUFFIXES


def build_pack_inventory(paths: list[Path]) -> PackInventory:
    """Inspect local copies. Never send workbook bytes to the model."""
    files = [inspect_file(path) for path in paths]
    present = {item.filename.lower() for item in files}
    missing: list[str] = []
    for item in files:
        for link in item.links:
            book = link.workbook
            key = Path(book).name.lower()
            link.present_in_pack = key in present
            if not link.present_in_pack and book not in missing:
                missing.append(book)
    return PackInventory(files=files, missing_links=missing)


def inspect_file(path: Path) -> FileInventory:
    filename = path.name
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return _inspect_csv(path)
        if suffix in {".xlsx", ".xlsm"}:
            return _inspect_excel(path)
        return FileInventory(
            filename=filename,
            kind=suffix.lstrip(".") or "unknown",
            unreadable=True,
            issues=["This file type is not supported."],
        )
    except Exception:
        return FileInventory(
            filename=filename,
            kind=suffix.lstrip(".") or "unknown",
            unreadable=True,
            issues=["This file could not be read. Try saving it again from Excel."],
        )


def _inspect_csv(path: Path) -> FileInventory:
    frame = _read_csv(path)
    sheet = _sheet_from_frame(path.stem or "Sheet", frame)
    issues: list[str] = []
    issues.extend(sheet.empty_notes)
    return FileInventory(
        filename=path.name,
        kind="csv",
        sheets=[sheet],
        issues=issues,
    )


def _read_csv(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        return pd.read_csv(path, encoding="latin-1", encoding_errors="replace")
    return pd.read_csv(path)


def _inspect_excel(path: Path) -> FileInventory:
    features = detect_excel_features(path)
    workbook = load_workbook(path, data_only=False, read_only=False)
    try:
        index_map = _external_index_map(workbook)
        sheets: list[SheetInfo] = []
        formulas: list[FormulaInfo] = []
        issues: list[str] = []
        for worksheet in workbook.worksheets:
            sheet, sheet_formulas, sheet_issues = _inspect_worksheet(
                worksheet, index_map
            )
            sheets.append(sheet)
            formulas.extend(sheet_formulas)
            issues.extend(sheet_issues)
        named = list(_iter_named_ranges(workbook))
        formula_total = len(formulas)
        kept_formulas = _select_formulas(formulas, MAX_FORMULAS_PER_FILE)
        kept_formulas = _follow_formula_targets(
            formulas, kept_formulas, MAX_FORMULAS_PER_FILE
        )
        if formula_total > MAX_FORMULAS_PER_FILE:
            issues.append(
                f"{path.name} has {formula_total} stored formulas; "
                f"listing {len(kept_formulas)} of {formula_total}."
            )
        links = _links_from_formulas(formulas)
        for item in named:
            for book in _books_in_text(item.refers_to, index_map):
                links.append(
                    ExternalLinkInfo(workbook=book, used_in=item.name)
                )
        links = _dedupe_links(links)
        return FileInventory(
            filename=path.name,
            kind=path.suffix.lower().lstrip("."),
            sheets=sheets,
            named_ranges=named,
            formulas=kept_formulas,
            links=links,
            features=features,
            issues=issues,
            formula_total=formula_total,
        )
    finally:
        workbook.close()


def detect_excel_features(path: Path) -> FeatureFlags:
    """Flag VBA / Power Query / Pivot / DAX as present. Do not interpret them."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = [item.filename.replace("\\", "/") for item in archive.infolist()]
    except zipfile.BadZipFile:
        return FeatureFlags()

    lowered = [name.lower() for name in names]
    return FeatureFlags(
        vba=any(name == "xl/vbaproject.bin" for name in lowered),
        power_query=any(
            name == "xl/connections.xml" or name.startswith("xl/querytables/")
            for name in lowered
        ),
        pivot=any(
            name.startswith("xl/pivotcache/") or name.startswith("xl/pivottables/")
            for name in lowered
        ),
        dax=any(
            name.startswith("xl/model/") or "powerpivot" in name for name in lowered
        ),
    )


def _inspect_worksheet(
    worksheet: Any, index_map: dict[str, str]
) -> tuple[SheetInfo, list[FormulaInfo], list[str]]:
    max_row = int(worksheet.max_row or 1)
    max_col = int(worksheet.max_column or 1)
    truncated = max_row > MAX_SCAN_ROWS or max_col > MAX_SCAN_COLS
    scan_rows = min(max_row, MAX_SCAN_ROWS)
    scan_cols = min(max_col, MAX_SCAN_COLS)
    hidden = str(getattr(worksheet, "sheet_state", "visible")) != "visible"

    first_values = [
        worksheet.cell(1, col).value for col in range(1, scan_cols + 1)
    ]
    header_row = 2 if _row_is_title(first_values) else 1
    headers: list[str] = []
    for col in range(1, scan_cols + 1):
        headers.append(_header_name(worksheet.cell(header_row, col).value, col))

    columns_data: list[list[Any]] = [[] for _ in headers]
    formulas: list[FormulaInfo] = []
    used_rows = 0
    empty_interior = 0
    saw_data = False

    for row_idx in range(1, scan_rows + 1):
        values = [worksheet.cell(row_idx, col).value for col in range(1, scan_cols + 1)]
        if row_idx <= header_row:
            continue
        if _row_empty(values):
            if saw_data:
                empty_interior += 1
            continue
        saw_data = True
        used_rows += 1
        row_label = _row_label(worksheet, row_idx)
        for col_idx, value in enumerate(values):
            if _is_formula(value):
                cell = f"{worksheet.title}!{get_column_letter(col_idx + 1)}{row_idx}"
                formula = _clip(str(value), MAX_FORMULA_CHARS)
                header = headers[col_idx] if col_idx < len(headers) else ""
                formulas.append(
                    FormulaInfo(
                        cell=cell,
                        formula=formula,
                        external_books=_books_in_text(str(value), index_map),
                        label=row_label,
                        column_header=header,
                    )
                )
            columns_data[col_idx].append(value)

    seen: dict[str, int] = {}
    columns: list[ColumnInfo] = []
    empty_notes: list[str] = []
    for header, raw_values in zip(headers[:MAX_COLUMNS], columns_data[:MAX_COLUMNS]):
        count = seen.get(header, 0) + 1
        seen[header] = count
        display = header if count == 1 else f"{header} ({count})"
        column = _column_from_values(display, raw_values)
        if count > 1:
            column.issues.append("Duplicate column name.")
        if header.startswith("Column ") and header[7:].isalpha():
            column.issues.append("Missing header.")
        columns.append(column)
        if "empty column" in " ".join(column.issues).lower():
            empty_notes.append(f"{worksheet.title} / {display} is an empty column.")

    if used_rows == 0 and all(item.startswith("Column ") for item in headers):
        empty_notes.append(f"{worksheet.title} looks empty.")
    if empty_interior:
        empty_notes.append(
            f"{worksheet.title} has {empty_interior} empty row(s) inside the used range."
        )
    if truncated:
        empty_notes.append(
            f"{worksheet.title} is large; only the first {scan_rows} rows and "
            f"{scan_cols} columns were read."
        )

    issues = list(empty_notes)
    if hidden:
        issues.append(f"{worksheet.title} is hidden.")

    sheet = SheetInfo(
        name=worksheet.title,
        row_count=used_rows,
        column_count=len(columns),
        columns=columns,
        empty_notes=empty_notes,
        hidden=hidden,
        truncated=truncated,
    )
    return sheet, formulas, issues


def _sheet_from_frame(name: str, frame: pd.DataFrame) -> SheetInfo:
    scan = frame.head(MAX_SCAN_ROWS)
    truncated = len(frame) > MAX_SCAN_ROWS or len(frame.columns) > MAX_SCAN_COLS
    if len(scan.columns) > MAX_SCAN_COLS:
        scan = scan.iloc[:, :MAX_SCAN_COLS]
    headers = [_header_name(column, idx + 1) for idx, column in enumerate(scan.columns)]
    seen: dict[str, int] = {}
    columns: list[ColumnInfo] = []
    empty_notes: list[str] = []
    for header, column_name in zip(headers, scan.columns):
        count = seen.get(header, 0) + 1
        seen[header] = count
        display = header if count == 1 else f"{header} ({count})"
        raw = [None if pd.isna(value) else value for value in scan[column_name].tolist()]
        column = _column_from_values(display, raw)
        if count > 1:
            column.issues.append("Duplicate column name.")
        columns.append(column)
        if "empty column" in " ".join(column.issues).lower():
            empty_notes.append(f"{name} / {display} is an empty column.")
    used_rows = int((~scan.isna().all(axis=1)).sum()) if len(scan) else 0
    if used_rows == 0 and not len(scan.columns):
        empty_notes.append(f"{name} looks empty.")
    if truncated:
        empty_notes.append(
            f"{name} is large; only the first {min(len(frame), MAX_SCAN_ROWS)} "
            f"rows were read."
        )
    return SheetInfo(
        name=name,
        row_count=used_rows,
        column_count=len(columns),
        columns=columns,
        empty_notes=empty_notes,
        truncated=truncated,
    )


def _column_from_values(name: str, values: list[Any]) -> ColumnInfo:
    non_empty = [value for value in values if not _is_empty(value)]
    total = len(values)
    empty_ratio = 1.0 if total == 0 else (total - len(non_empty)) / total
    types = {_infer_type(value) for value in non_empty if not _is_formula(value)}
    types.discard("empty")
    if not types:
        inferred = "empty" if not non_empty else "formula"
    elif len(types) == 1:
        inferred = next(iter(types))
    else:
        inferred = "mixed"
    issues: list[str] = []
    if inferred == "empty" or (total > 0 and empty_ratio >= EMPTY_COLUMN_RATIO and not non_empty):
        issues.append("Empty column.")
    elif empty_ratio >= EMPTY_COLUMN_RATIO and non_empty:
        issues.append("Mostly empty column.")
    if inferred == "mixed":
        issues.append("Mixed types.")
    samples = [_sample_text(value) for value in non_empty if not _is_formula(value)]
    samples = [item for item in samples if item][:MAX_SAMPLE_VALUES]
    return ColumnInfo(
        name=name,
        inferred_type=inferred,
        samples=samples,
        empty_ratio=round(empty_ratio, 3),
        issues=issues,
    )


def _row_is_title(values: list[Any]) -> bool:
    """True when row 1 is a long title, not a header row."""
    filled = [value for value in values if not _is_empty(value)]
    if len(filled) != 1 or _is_formula(filled[0]):
        return False
    text = " ".join(str(filled[0]).split())
    return len(text) >= TITLE_ROW_MIN_CHARS


def _row_label(worksheet: Any, row_idx: int) -> str:
    raw = worksheet.cell(row_idx, 1).value
    if _is_empty(raw) or _is_formula(raw):
        return ""
    if _infer_type(raw) != "text":
        return ""
    return _clip(" ".join(str(raw).split()), MAX_LABEL_CHARS)


def _is_empty_column(column: ColumnInfo) -> bool:
    return column.inferred_type == "empty" or "Empty column." in column.issues


def _formula_bucket(item: FormulaInfo) -> int:
    """Lower is kept first: links, finance terms, lookups, cross-sheet, rest."""
    formula_l = item.formula.lower()
    extra = " ".join(
        part.lower()
        for part in (item.cell, item.label, item.column_header)
        if part
    )
    if item.external_books:
        return 0
    if any(term in formula_l or term in extra for term in _FINANCE_TERMS):
        return 1
    if "vlookup" in formula_l or "xlookup" in formula_l:
        return 2
    if "!" in item.formula:
        return 3
    return 4


def _select_formulas(
    formulas: list[FormulaInfo],
    limit: int = MAX_FORMULAS_PER_FILE,
    per_sheet: int = MAX_FORMULAS_PER_SHEET,
) -> list[FormulaInfo]:
    ranked = [
        item
        for _, item in sorted(
            enumerate(formulas),
            key=lambda pair: (_formula_bucket(pair[1]), pair[0]),
        )
    ]
    selected: list[FormulaInfo] = []
    leftover: list[FormulaInfo] = []
    counts: dict[str, int] = {}
    for item in ranked:
        sheet = item.cell.split("!", 1)[0]
        if counts.get(sheet, 0) >= per_sheet:
            leftover.append(item)
            continue
        selected.append(item)
        counts[sheet] = counts.get(sheet, 0) + 1
        if len(selected) >= limit:
            return selected
    for item in leftover:
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _follow_formula_targets(
    all_formulas: list[FormulaInfo],
    selected: list[FormulaInfo],
    limit: int,
) -> list[FormulaInfo]:
    """If a kept formula points at another stored cell, keep that target too."""
    by_cell = {item.cell: item for item in all_formulas}
    seen = {item.cell for item in selected}
    extras: list[FormulaInfo] = []
    for item in selected:
        for match in _SHEET_CELL.finditer(item.formula):
            sheet = match.group(1) or match.group(2)
            target = f"{sheet}!{match.group(3)}{match.group(4)}"
            found = by_cell.get(target)
            if found is None or found.cell in seen:
                continue
            extras.append(found)
            seen.add(found.cell)
    if not extras:
        return selected
    merged = selected[:1]
    inserted = {selected[0].cell}
    # Keep the first (highest-ranked) line, then its targets, then the rest.
    for extra in extras:
        if extra.cell not in inserted:
            merged.append(extra)
            inserted.add(extra.cell)
        if len(merged) >= limit:
            return merged
    for item in selected[1:]:
        if item.cell in inserted:
            continue
        merged.append(item)
        inserted.add(item.cell)
        if len(merged) >= limit:
            break
    return merged


def _header_name(value: Any, col_index: int) -> str:
    if _is_empty(value) or _is_formula(value):
        return f"Column {get_column_letter(col_index)}"
    text = " ".join(str(value).split())
    return text[:80] if text else f"Column {get_column_letter(col_index)}"


def _infer_type(value: Any) -> str:
    if _is_empty(value):
        return "empty"
    if isinstance(value, bool):
        return "text"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return "date"
    text = str(value).strip()
    if not text:
        return "empty"
    if _looks_like_number(text):
        return "number"
    if _looks_like_date(text):
        return "date"
    return "text"


def _looks_like_number(text: str) -> bool:
    cleaned = text.replace(",", "").replace(" ", "")
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _looks_like_date(text: str) -> bool:
    if len(text) < 6:
        return False
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            datetime.strptime(text[:10], fmt)
            return True
        except ValueError:
            continue
    return False


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _row_empty(values: list[Any]) -> bool:
    return all(_is_empty(value) for value in values)


def _sample_text(value: Any) -> str:
    if isinstance(value, datetime):
        text = value.strftime("%Y-%m-%d")
    else:
        text = " ".join(str(value).split())
    return _clip(text, MAX_SAMPLE_CHARS)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _external_index_map(workbook: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    links = getattr(workbook, "_external_links", None) or []
    for index, link in enumerate(links, start=1):
        target = _external_link_target(link)
        if target:
            mapping[str(index)] = target
    return mapping


def _external_link_target(link: Any) -> str:
    file_link = getattr(link, "file_link", None)
    target = getattr(file_link, "target", None) if file_link is not None else None
    if target is None:
        target = getattr(link, "Target", None) or getattr(link, "target", None)
    if not target:
        return ""
    name = Path(str(target).replace("\\", "/")).name
    return name or str(target)


def _iter_named_ranges(workbook: Any) -> list[NamedRangeInfo]:
    defined = getattr(workbook, "defined_names", None)
    if defined is None:
        return []
    found: list[NamedRangeInfo] = []
    try:
        names = list(defined)
    except TypeError:
        return []
    for name in names:
        try:
            defn = defined[name]
        except Exception:
            continue
        text = (
            getattr(defn, "attr_text", None)
            or getattr(defn, "value", None)
            or str(defn)
        )
        found.append(NamedRangeInfo(name=str(name), refers_to=str(text)))
    return found


def _books_in_text(text: str, index_map: dict[str, str]) -> list[str]:
    books: list[str] = []
    for match in _BRACKET_REF.findall(text):
        token = match.strip("'")
        if _INDEXED_BOOK.match(token):
            resolved = index_map.get(token, f"external workbook #{token}")
        else:
            resolved = Path(token.replace("\\", "/")).name or token
        if resolved not in books:
            books.append(resolved)
    return books


def _links_from_formulas(formulas: list[FormulaInfo]) -> list[ExternalLinkInfo]:
    links: list[ExternalLinkInfo] = []
    for item in formulas:
        for book in item.external_books:
            links.append(ExternalLinkInfo(workbook=book, used_in=item.cell))
    return _dedupe_links(links)


def _dedupe_links(links: list[ExternalLinkInfo]) -> list[ExternalLinkInfo]:
    seen: set[tuple[str, str]] = set()
    unique: list[ExternalLinkInfo] = []
    for item in links:
        key = (item.workbook.lower(), item.used_in)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def format_english(pack: PackInventory) -> str:
    lines = ["## Workbook inventory", ""]
    if not pack.files:
        lines.append("No Excel or CSV files were attached.")
        return "\n".join(lines)

    lines.append(f"{len(pack.files)} file(s) in this chat. Later questions reuse this inventory.")
    lines.append("")
    for item in pack.files:
        lines.extend(_english_file(item))
        lines.append("")

    if pack.missing_links:
        missing = ", ".join(pack.missing_links)
        lines.append("### Missing linked workbooks")
        lines.append(
            f"These files are referenced but were not attached: {missing}. "
            "Attach the folder that contains them if you need those links."
        )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _english_file(item: FileInventory) -> list[str]:
    if item.unreadable:
        return [
            f"**{item.filename}** — this file could not be read. "
            "Try saving it again from Excel."
        ]
    kind = "CSV" if item.kind == "csv" else "Excel"
    sheet_word = "sheet" if len(item.sheets) == 1 else "sheets"
    lines = [f"**{item.filename}** — {kind}, {len(item.sheets)} {sheet_word}"]
    for sheet in item.sheets:
        hidden = " (hidden)" if sheet.hidden else ""
        col_bits = [
            f"{column.name} ({column.inferred_type})" for column in sheet.columns
        ]
        columns = ", ".join(col_bits) if col_bits else "no columns"
        lines.append(
            f"- **{sheet.name}**{hidden} — {sheet.row_count} data rows, columns {columns}."
        )
        if sheet.empty_notes:
            for note in sheet.empty_notes:
                lines.append(f"  - {note}")

    if item.formulas:
        extra = ""
        if item.formula_total > len(item.formulas):
            extra = f" (showing {len(item.formulas)} of {item.formula_total})"
        lines.append(f"- Stored formulas{extra}:")
        for formula in item.formulas:
            lines.append(f"  - `{formula.cell}`: `{formula.formula}`")
    else:
        lines.append("- Stored formulas: none found.")

    if item.named_ranges:
        lines.append("- Named ranges:")
        for named in item.named_ranges:
            lines.append(f"  - {named.name} → `{named.refers_to}`")

    if item.links:
        lines.append("- External links:")
        for link in item.links:
            state = "in this pack" if link.present_in_pack else "missing from this pack"
            lines.append(f"  - `{link.used_in}` reads **{link.workbook}** ({state})")

    feature_bits = _feature_phrases(item.features)
    if feature_bits:
        lines.append(
            "- Also found (present, not interpreted): " + "; ".join(feature_bits) + "."
        )
    return lines


def _feature_phrases(features: FeatureFlags) -> list[str]:
    bits: list[str] = []
    if features.vba:
        bits.append("VBA macros")
    if features.power_query:
        bits.append("Power Query or data connections")
    if features.pivot:
        bits.append("Pivot tables")
    if features.dax:
        bits.append("DAX / Power Pivot")
    return bits


def format_prompt(pack: PackInventory, *, budget: int = MAX_PROMPT_CHARS) -> str:
    """Named ranges, links, and formulas first. Trim sheets before formulas."""
    marker = f"\n{TRIM_MARKER}"
    reserved = len(marker)
    candidates = (
        _prompt_body(pack, include_samples=True, include_sheets=True),
        _prompt_body(pack, include_samples=False, include_sheets=True),
        _prompt_body(pack, include_samples=False, include_sheets=False),
    )
    for text in candidates:
        if len(text) <= budget:
            return text
    lines = candidates[-1].splitlines()
    while lines and len("\n".join(lines)) + reserved > budget:
        if not lines[-1].startswith("  FORMULA"):
            break
        lines.pop()
    listed = sum(1 for line in lines if line.startswith("  FORMULA"))
    for index, line in enumerate(lines):
        if line.startswith("FORMULAS "):
            total = line.split(" of ", 1)[-1]
            lines[index] = f"FORMULAS {listed} of {total}"
            break
    fitted = "\n".join(lines)
    if len(fitted) + reserved <= budget:
        return fitted + marker
    trimmed = fitted[: max(0, budget - reserved)].rstrip()
    if "\n" in trimmed:
        trimmed = trimmed.rsplit("\n", 1)[0]
    return trimmed + marker


def _prompt_body(
    pack: PackInventory,
    *,
    include_samples: bool,
    include_sheets: bool = True,
) -> str:
    names: list[str] = []
    links: list[str] = []
    formulas: list[str] = []
    formula_total = 0
    sheets: list[str] = []
    features: list[str] = []
    unreadable: list[str] = []
    multi = len(pack.files) > 1

    for item in pack.files:
        if item.unreadable:
            unreadable.append(f"FILE {item.filename} UNREADABLE")
            continue
        prefix = f"{item.filename} " if multi else ""
        if item.named_ranges:
            for named in item.named_ranges:
                names.append(f"  {prefix}{named.name} {named.refers_to}")
        if item.links:
            for link in item.links:
                state = "present" if link.present_in_pack else "missing"
                links.append(
                    f"  {prefix}{link.used_in} -> [{link.workbook}] ({state})"
                )
        formula_total += item.formula_total or len(item.formulas)
        for formula in item.formulas:
            label = f" | {formula.label}" if formula.label else ""
            formulas.append(
                f"  FORMULA {prefix}{formula.cell} {formula.formula}{label}"
            )
        if include_sheets:
            for sheet in item.sheets:
                col_bits: list[str] = []
                for column in sheet.columns:
                    if _is_empty_column(column):
                        continue
                    bit = f"{column.name}:{column.inferred_type}"
                    if include_samples and column.samples:
                        bit += f" samples={','.join(column.samples)}"
                    col_bits.append(bit)
                hidden = " hidden=1" if sheet.hidden else ""
                sheet_prefix = f"{item.filename} " if multi else ""
                cols = f" cols={'; '.join(col_bits)}" if col_bits else ""
                sheets.append(
                    f"  {sheet_prefix}{sheet.name} rows={sheet.row_count}{hidden}{cols}"
                )
        if item.features.any():
            flags = _feature_flag_tokens(item.features)
            features.append(f"  {prefix}FEATURES {','.join(flags)} (detect only)")

    lines = ["PACK " + ", ".join(pack.filenames())]
    if pack.missing_links:
        lines.append("MISSING " + ", ".join(pack.missing_links))
    lines.extend(unreadable)
    if names:
        lines.append("NAMED_RANGES")
        lines.extend(names)
    else:
        lines.append("NAMED_RANGES none")
    if links:
        lines.append("EXTERNAL_LINKS")
        lines.extend(links)
    else:
        lines.append("EXTERNAL_LINKS none")
    listed = len(formulas)
    lines.append(f"FORMULAS {listed} of {formula_total}")
    lines.extend(formulas)
    if include_sheets and sheets:
        lines.append("SHEETS")
        lines.extend(sheets)
    lines.extend(features)
    return "\n".join(lines)


def _feature_flag_tokens(features: FeatureFlags) -> list[str]:
    flags: list[str] = []
    if features.vba:
        flags.append("vba")
    if features.power_query:
        flags.append("power_query")
    if features.pivot:
        flags.append("pivot")
    if features.dax:
        flags.append("dax")
    return flags
