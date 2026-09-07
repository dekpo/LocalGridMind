"""Post-check model replies against listed formulas. No GGUF."""

from __future__ import annotations

from pathlib import Path

from src.core.ground import ground_from_json, ground_model_reply
from src.core.inventory import build_pack_inventory
from src.core.lookup import answer_inventory_question, classify_inventory_intent
from tests.workbook_fixtures import write_wacc_pack_xlsx


def test_wrong_b13_formula_is_corrected(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    reply = "Cost of capital!B13 is `=1+1`, which is a simple sum."
    grounded = ground_model_reply(reply, pack)
    assert grounded.startswith(reply)
    assert grounded != reply
    assert "=B10*B11+B12" in grounded
    assert "not `=1+1`" in grounded
    assert "JSON" not in grounded
    assert "GGUF" not in grounded
    from_json = ground_from_json(reply, pack.to_json())
    assert from_json == grounded


def test_matching_b13_formula_is_left_alone(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    reply = "Cost of capital!B13 is `=B10*B11+B12`."
    assert ground_model_reply(reply, pack) == reply


def test_bare_c9_assignment_is_corrected_when_unique() -> None:
    from src.core.inventory import FileInventory, FormulaInfo, PackInventory

    pack = PackInventory(
        files=[
            FileInventory(
                filename="model.xlsx",
                kind="xlsx",
                formulas=[
                    FormulaInfo(
                        cell="Valuation output!C9",
                        formula="=C7-C8",
                        label="FCFF",
                    )
                ],
                formula_total=1,
            )
        ]
    )
    reply = "A paste-ready FCFF formula is C9: =M7-M8."
    grounded = ground_model_reply(reply, pack)
    assert "=C7-C8" in grounded
    assert "not `=M7-M8`" in grounded
    assert reply in grounded


def test_how_is_terminal_value_still_skips_lookup(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    question = "How is terminal value calculated?"
    assert classify_inventory_intent(question) is None
    assert answer_inventory_question(question, pack) is None
    reply = "Terminal value uses the growth identity shown on that sheet."
    assert ground_model_reply(reply, pack) == reply
