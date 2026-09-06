"""Tiny synthetic workbooks for Phase 6 tests. Never use client files."""

from __future__ import annotations

import zipfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.workbook.defined_name import DefinedName


def write_books_xlsx(path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Books"
    sheet.append(["Book", "Name"])
    sheet.append(["A", "Alpha"])
    sheet.append(["B", "Bravo"])
    workbook.save(path)
    workbook.close()
    return path


def write_rates_xlsx(path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rates"
    sheet.append(["Date", "Book", "Rate", "Notes"])
    sheet.append(["2026-01-01", "A", 1.5, None])
    sheet.append(["2026-01-02", "B", 2.0, None])
    sheet["E2"] = "=[Books.xlsx]Books!B2"
    sheet["E3"] = "=C3*1"
    workbook.defined_names.add(
        DefinedName(name="RateTable", attr_text="Rates!$A$1:$C$3")
    )
    workbook.save(path)
    workbook.close()
    return path


def write_wacc_pack_xlsx(path: Path) -> Path:
    """Damodaran-shaped single workbook: title row, WACC pointer, empty cols."""
    workbook = Workbook()
    inputs = workbook.active
    inputs.title = "Input sheet"
    inputs["A1"] = (
        "FCFF Simple Ginzu — illustration workbook for cost of capital tests"
    )
    inputs["A2"] = "Item"
    inputs["B2"] = "Value"
    inputs["C2"] = "Note"
    for row in range(3, 11):
        inputs[f"A{row}"] = f"Input {row}"
        inputs[f"B{row}"] = row
        inputs[f"C{row}"] = "keep"
    inputs["A20"] = "Industry lookup"
    inputs["B20"] = "=VLOOKUP(B3,'Cost of capital'!A10:C13,2,FALSE)"
    inputs["A35"] = "Initial cost of capital"
    inputs["B35"] = "='Cost of capital'!B13"
    inputs["J40"] = ""

    cost = workbook.create_sheet("Cost of capital")
    cost["A10"] = "Equity weight"
    cost["B10"] = 0.6
    cost["A11"] = "Cost of equity"
    cost["B11"] = 0.1
    cost["A12"] = "Debt component"
    cost["B12"] = 0.02
    cost["A13"] = "Cost of capital"
    cost["B13"] = "=B10*B11+B12"

    valuation = workbook.create_sheet("Valuation output")
    valuation["A1"] = "Year"
    valuation["B1"] = "FCFF"
    valuation["A20"] = "Terminal value"
    valuation["F20"] = 100
    valuation["G20"] = 0.03
    valuation["L20"] = "=F20*(1+G20)/('Cost of capital'!B13-G20)"
    valuation["P22"] = ""

    workbook.defined_names.add(
        DefinedName(name="RateTable", attr_text="'Input sheet'!$A$2:$C$10")
    )
    workbook.save(path)
    workbook.close()
    return path


def write_mixed_csv(path: Path) -> Path:
    path.write_text(
        "id,amount,note,spare\n"
        "1,10,hello,\n"
        "2,x,world,\n",
        encoding="utf-8",
    )
    return path


def add_zip_members(path: Path, members: dict[str, bytes]) -> Path:
    tmp = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp, "w") as dest:
        for info in source.infolist():
            dest.writestr(info, source.read(info.filename))
        for name, data in members.items():
            dest.writestr(name, data)
    tmp.replace(path)
    return path
