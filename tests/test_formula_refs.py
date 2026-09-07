"""Deterministic [[FORMULA:Sheet!A1]] resolution. No GGUF."""

from __future__ import annotations

import json

from src.core.formula_refs import (
    COMPETING_NOTE,
    UNVERIFIED_NOTICE,
    resolve_formula_ref,
    resolve_formula_refs,
    resolve_formula_refs_from_json,
)
from src.core.inventory import FileInventory, FormulaInfo, PackInventory
from src.core.lookup import answer_inventory_question
from src.core.prompt import INVENTORY_PREAMBLE, build_chat_prompt


def _pack(*rows: tuple[str, str, str]) -> PackInventory:
    """Build a pack from (filename, cell, formula) rows."""
    files: dict[str, FileInventory] = {}
    for filename, cell, formula in rows:
        item = files.get(filename)
        if item is None:
            item = FileInventory(filename=filename, kind="xlsx")
            files[filename] = item
        info = FormulaInfo(cell=cell, formula=formula)
        item.all_formulas.append(info)
        item.formula_total = len(item.all_formulas)
    return PackInventory(files=list(files.values()))


def test_exact_formula_ref_is_resolved_from_inventory() -> None:
    pack = _pack(
        ("model.xlsx", "Valuation output!B18", "=B16/(B17-M2)"),
    )
    text = "The formula is [[FORMULA:Valuation output!B18]]."
    resolved, errors = resolve_formula_refs(text, pack)
    assert errors == []
    assert "Valuation output!B18" in resolved
    assert "=B16/(B17-M2)" in resolved
    assert "[[FORMULA:" not in resolved
    found = resolve_formula_ref("Valuation output!B18", pack)
    assert found is not None
    assert found.formula == "=B16/(B17-M2)"


def test_missing_formula_ref_fails_closed() -> None:
    pack = _pack(
        ("model.xlsx", "Valuation output!B18", "=B16/(B17-M2)"),
    )
    text = "The formula is [[FORMULA:Valuation output!B999]]."
    resolved, errors = resolve_formula_refs(text, pack)
    assert errors == ["Valuation output!B999"]
    assert "=B16/(B17-M2)" not in resolved
    assert "B999" in resolved
    assert "could not be verified" in resolved
    assert UNVERIFIED_NOTICE in resolved
    assert resolve_formula_ref("Valuation output!B999", pack) is None


def test_same_address_on_two_sheets_resolves_independently() -> None:
    pack = _pack(
        ("model.xlsx", "Sheet1!B18", "=SUM(A1:A10)"),
        ("model.xlsx", "Sheet2!B18", "=AVERAGE(A1:A10)"),
    )
    text = (
        "First [[FORMULA:Sheet1!B18]] then [[FORMULA:Sheet2!B18]]."
    )
    resolved, errors = resolve_formula_refs(text, pack)
    assert errors == []
    assert "Sheet1!B18 → =SUM(A1:A10)" in resolved
    assert "Sheet2!B18 → =AVERAGE(A1:A10)" in resolved


def test_suggested_formula_is_left_intact() -> None:
    pack = _pack(("model.xlsx", "Sheet1!B18", "=SUM(A1:A10)"))
    text = (
        "You could add this instead.\n"
        "SUGGESTED FORMULA:\n"
        "=XLOOKUP(A2,Data!A:A,Data!B:B)"
    )
    resolved, errors = resolve_formula_refs(text, pack)
    assert errors == []
    assert resolved == text
    assert "=XLOOKUP(A2,Data!A:A,Data!B:B)" in resolved


def test_raw_hallucinated_formula_is_not_verified() -> None:
    pack = _pack(
        ("model.xlsx", "Valuation output!B18", "=B16/(B17-M2)"),
    )
    text = "The formula is =B16/(B17-M3)."
    resolved, errors = resolve_formula_refs(text, pack)
    assert errors == []
    assert resolved == text
    assert "→ =B16/(B17-M2)" not in resolved
    assert "[[FORMULA:" not in text


def test_competing_formula_after_ref_is_not_official() -> None:
    pack = _pack(("model.xlsx", "Sheet1!B18", "=B16/(B17-M2)"))
    text = "[[FORMULA:Sheet1!B18]]\nwhich is =B16/(B17-M3)"
    resolved, errors = resolve_formula_refs(text, pack)
    assert errors == []
    assert "Sheet1!B18 → =B16/(B17-M2)" in resolved
    assert COMPETING_NOTE.format(cell="Sheet1!B18", stored="=B16/(B17-M2)") in resolved
    official = resolved.split("which is", 1)[0]
    assert "=B16/(B17-M2)" in official
    assert "=B16/(B17-M3)" not in official


def test_formula_absent_from_prompt_list_still_resolves() -> None:
    hidden = FormulaInfo(cell="Valuation output!B18", formula="=B16/(B17-M2)")
    pack = PackInventory(
        files=[
            FileInventory(
                filename="big.xlsx",
                kind="xlsx",
                formulas=[
                    FormulaInfo(
                        cell="Input sheet!B35",
                        formula="='Cost of capital'!B13",
                    )
                ],
                all_formulas=[
                    FormulaInfo(
                        cell="Input sheet!B35",
                        formula="='Cost of capital'!B13",
                    ),
                    hidden,
                ],
                formula_total=2,
            )
        ]
    )
    resolved, errors = resolve_formula_refs(
        "See [[FORMULA:Valuation output!B18]].", pack
    )
    assert errors == []
    assert "Valuation output!B18 → =B16/(B17-M2)" in resolved
    answer = answer_inventory_question(
        "What does Valuation output!B18 do?", pack
    )
    assert answer is not None
    assert "=B16/(B17-M2)" in answer


def test_old_pack_json_without_all_formulas_still_resolves() -> None:
    pack = PackInventory(
        files=[
            FileInventory(
                filename="legacy.xlsx",
                kind="xlsx",
                formulas=[
                    FormulaInfo(cell="Sheet1!B18", formula="=B16/(B17-M2)")
                ],
                formula_total=1,
            )
        ]
    )
    raw = json.loads(pack.to_json())
    for item in raw["files"]:
        item.pop("all_formulas", None)
    restored = PackInventory.from_json(json.dumps(raw))
    assert restored.files[0].all_formulas == []
    resolved, errors = resolve_formula_refs_from_json(
        "[[FORMULA:Sheet1!B18]]", json.dumps(raw)
    )
    assert errors == []
    assert "Sheet1!B18 → =B16/(B17-M2)" in resolved


def test_ambiguous_same_cell_two_workbooks_fails_closed() -> None:
    pack = _pack(
        ("alpha.xlsx", "Sheet1!B18", "=SUM(A1:A10)"),
        ("beta.xlsx", "Sheet1!B18", "=AVERAGE(A1:A10)"),
    )
    resolved, errors = resolve_formula_refs("[[FORMULA:Sheet1!B18]]", pack)
    assert errors == ["Sheet1!B18"]
    assert "SUM" not in resolved
    assert "AVERAGE" not in resolved
    qualified, ok = resolve_formula_refs(
        "[[FORMULA:alpha.xlsx::Sheet1!B18]]", pack
    )
    assert ok == []
    assert "Sheet1!B18 → =SUM(A1:A10)" in qualified


def test_resolved_formula_keeps_stored_characters() -> None:
    pack = _pack(
        ("model.xlsx", "Valuation output!B18", "=B16/(B17-M2)"),
    )
    resolved, errors = resolve_formula_refs(
        "[[FORMULA:Valuation output!B18]]", pack
    )
    assert errors == []
    assert "=B16/(B17-M2)" in resolved
    assert "=B16 / (B17 - M2)" not in resolved


def test_workbook_plus_unique_a1_resolves() -> None:
    pack = _pack(
        ("Rates.xlsx", "Rates!E2", "=[Books.xlsx]Books!B2"),
        ("Books.xlsx", "Books!A2", "=1"),
    )
    resolved, errors = resolve_formula_refs("[[FORMULA:Rates.xlsx!E2]]", pack)
    assert errors == []
    assert "Rates!E2 → =[Books.xlsx]Books!B2" in resolved
    found = resolve_formula_ref("Rates.xlsx!E2", pack)
    assert found is not None
    assert found.formula == "=[Books.xlsx]Books!B2"


def test_workbook_plus_ambiguous_a1_fails_closed() -> None:
    pack = _pack(
        ("model.xlsx", "Sheet1!E2", "=SUM(A1:A10)"),
        ("model.xlsx", "Sheet2!E2", "=AVERAGE(A1:A10)"),
    )
    resolved, errors = resolve_formula_refs("[[FORMULA:model.xlsx!E2]]", pack)
    assert errors == ["model.xlsx!E2"]
    assert "SUM" not in resolved
    assert "AVERAGE" not in resolved
    qualified, ok = resolve_formula_refs("[[FORMULA:model.xlsx!Sheet1!E2]]", pack)
    assert ok == []
    assert "Sheet1!E2 → =SUM(A1:A10)" in qualified


def test_prompt_still_asks_for_formula_references() -> None:
    text = build_chat_prompt("How is terminal value calculated?", "PACK model.xlsx")
    assert INVENTORY_PREAMBLE in text
    assert "[[FORMULA:Sheet Name!A1]]" in text
    assert "[[FORMULA:File.xlsx!A1]]" in text
    assert "SUGGESTED FORMULA:" in text
    assert "Do not invent cell addresses" in text
    assert "not in the inventory" in text
