"""Workbook inventory tests. Synthetic fixtures only — no client files or GGUF."""

from __future__ import annotations

from pathlib import Path

from src.core.inventory import (
    MAX_PROMPT_CHARS,
    PackInventory,
    build_pack_inventory,
    detect_excel_features,
    inspect_file,
)
from src.core.prompt import INVENTORY_PREAMBLE, build_chat_prompt
from tests.workbook_fixtures import (
    add_zip_members,
    write_books_xlsx,
    write_mixed_csv,
    write_rates_xlsx,
    write_wacc_pack_xlsx,
)


def test_csv_schema_types_samples_and_empty_column(tmp_path: Path) -> None:
    path = write_mixed_csv(tmp_path / "ledger.csv")
    inventory = inspect_file(path)

    assert inventory.filename == "ledger.csv"
    assert inventory.kind == "csv"
    assert inventory.unreadable is False
    sheet = inventory.sheets[0]
    names = [column.name for column in sheet.columns]
    assert names == ["id", "amount", "note", "spare"]
    types = {column.name: column.inferred_type for column in sheet.columns}
    assert types["id"] == "number"
    assert types["amount"] == "mixed"
    assert types["note"] == "text"
    assert types["spare"] == "empty"
    amount = next(column for column in sheet.columns if column.name == "amount")
    assert "Mixed types." in amount.issues
    spare = next(column for column in sheet.columns if column.name == "spare")
    assert spare.samples == []
    assert any("empty column" in note.lower() for note in sheet.empty_notes)


def test_excel_formulas_named_range_and_external_link(tmp_path: Path) -> None:
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    books = write_books_xlsx(tmp_path / "Books.xlsx")
    pack = build_pack_inventory([rates, books])

    rates_inv = next(item for item in pack.files if item.filename == "Rates.xlsx")
    cells = {item.cell: item.formula for item in rates_inv.formulas}
    assert "Rates!E2" in cells
    assert "[Books.xlsx]" in cells["Rates!E2"]
    assert any(item.name == "RateTable" for item in rates_inv.named_ranges)
    books_link = next(
        item for item in rates_inv.links if item.workbook == "Books.xlsx"
    )
    assert books_link.present_in_pack is True
    assert pack.missing_links == []

    english = pack.to_english()
    assert "Rates.xlsx" in english
    assert "Books.xlsx" in english
    assert "RateTable" in english
    assert "VBA macros" not in english
    prompt = pack.to_prompt()
    assert "FORMULA" in prompt
    assert "Rates!E2" in prompt
    assert "EXTERNAL_LINKS" in prompt
    assert "Books.xlsx" in prompt


def test_missing_linked_workbook_is_listed(tmp_path: Path) -> None:
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    pack = build_pack_inventory([rates])
    assert "Books.xlsx" in pack.missing_links
    english = pack.to_english()
    assert "Missing linked workbooks" in english
    assert "Books.xlsx" in english


def test_feature_flags_detect_only(tmp_path: Path) -> None:
    path = write_books_xlsx(tmp_path / "Flags.xlsx")
    add_zip_members(
        path,
        {
            "xl/vbaProject.bin": b"fake-vba",
            "xl/connections.xml": b"<connections/>",
            "xl/pivotCache/pivotCacheDefinition1.xml": b"<cache/>",
            "xl/model/tables.xml": b"<model/>",
        },
    )
    flags = detect_excel_features(path)
    assert flags.vba is True
    assert flags.power_query is True
    assert flags.pivot is True
    assert flags.dax is True

    inventory = inspect_file(path)
    english = inventory_to_english_snippet(inventory)
    assert "VBA macros" in english
    assert "not interpreted" in english
    assert "Power Query" in english
    assert "Pivot" in english
    assert "DAX" in english


def test_prompt_stays_compact_and_never_embeds_the_sheet(tmp_path: Path) -> None:
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    pack = build_pack_inventory([rates])
    prompt = pack.to_prompt(budget=80)
    assert len(prompt) <= 80
    assert "inventory trimmed" in prompt
    full = pack.to_prompt()
    assert len(full) <= MAX_PROMPT_CHARS
    assert "2026-01-01" not in full or full.count("2026-01-01") <= 1


def test_wacc_compact_prompt_keeps_formulas_before_sheet_noise(
    tmp_path: Path,
) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    tight = pack.to_prompt(budget=700)
    assert "B35" in tight
    assert "Cost of capital" in tight
    assert "Cost of capital!B13" in tight
    assert "=B10*B11+B12" in tight
    assert "NAMED_RANGES" in tight
    assert "RateTable" in tight
    assert "FORMULA" in tight
    formula_at = tight.index("FORMULA")
    assert "SHEETS" not in tight or formula_at < tight.index("SHEETS")
    assert "Column G:empty" not in tight
    assert "Column H:empty" not in tight
    assert "Column I:empty" not in tight


def test_named_ranges_none_is_explicit(tmp_path: Path) -> None:
    path = write_books_xlsx(tmp_path / "Books.xlsx")
    pack = build_pack_inventory([path])
    prompt = pack.to_prompt()
    assert "NAMED_RANGES none" in prompt
    assert "RateTable" not in prompt
    assert "Input mixed" not in prompt


def test_folder_pack_prompt_lists_present_and_missing_links(
    tmp_path: Path,
) -> None:
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    books = write_books_xlsx(tmp_path / "Books.xlsx")
    present = build_pack_inventory([rates, books])
    present_prompt = present.to_prompt()
    assert "EXTERNAL_LINKS" in present_prompt
    assert "Books.xlsx" in present_prompt
    assert "(present)" in present_prompt
    assert "EXTERNAL_LINKS none" not in present_prompt

    missing = build_pack_inventory([rates])
    missing_prompt = missing.to_prompt()
    assert "EXTERNAL_LINKS" in missing_prompt
    assert "Books.xlsx" in missing_prompt
    assert "(missing)" in missing_prompt
    assert "MISSING" in missing_prompt


def test_pack_json_roundtrip_keeps_wacc_formulas(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    restored = PackInventory.from_json(pack.to_json())
    cells = {
        item.cell
        for file in restored.files
        for item in file.formulas
    }
    assert "Input sheet!B35" in cells
    assert "Cost of capital!B13" in cells
    assert restored.files[0].formula_total == pack.files[0].formula_total


def test_build_chat_prompt_forbids_invented_cells() -> None:
    text = build_chat_prompt("Where is WACC?", "PACK wacc_pack.xlsx")
    assert INVENTORY_PREAMBLE in text
    assert "not in the inventory" in text
    assert "Do not invent cell addresses" in text
    assert "Do not invent numeric answers" in text
    assert "Do not write Python" in text


def test_unreadable_file_is_reported_in_english(tmp_path: Path) -> None:
    path = tmp_path / "Broken.xlsx"
    path.write_bytes(b"not-an-excel-file")
    inventory = inspect_file(path)
    assert inventory.unreadable is True
    pack = build_pack_inventory([path])
    assert "could not be read" in pack.to_english()


def inventory_to_english_snippet(inventory) -> str:
    from src.core.inventory import PackInventory, format_english

    return format_english(PackInventory(files=[inventory]))
