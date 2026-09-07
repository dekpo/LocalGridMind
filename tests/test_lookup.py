"""Deterministic inventory lookup. Synthetic fixtures only — no GGUF."""

from __future__ import annotations

from pathlib import Path

from src.core.inventory import (
    FileInventory,
    FormulaInfo,
    PackInventory,
    build_pack_inventory,
    parse_cell_addresses,
)
from src.core.lookup import (
    CELL_QUOTE,
    EXTERNAL_LINKS,
    FILE_READS,
    NAMED_RANGES,
    WHERE_COMPUTED,
    answer_from_json,
    answer_inventory_question,
    classify_inventory_intent,
)
from src.core.prompt import INVENTORY_PREAMBLE, build_chat_prompt
from tests.workbook_fixtures import (
    write_books_xlsx,
    write_rates_xlsx,
    write_wacc_pack_xlsx,
)


def test_wacc_where_is_returns_b35_and_b13(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    cached = PackInventory.from_json(pack.to_json())

    for question in (
        "Where is WACC or the cost of capital computed?",
        "Where is WACC computed?",
        "Where is the cost of capital computed?",
    ):
        answer = answer_inventory_question(question, cached)
        assert answer is not None
        assert "Input sheet!B35" in answer
        assert "Cost of capital!B13" in answer
        assert "Industry lookup" not in answer
        assert "Terminal value" not in answer


def test_books_only_named_ranges_are_none(tmp_path: Path) -> None:
    path = write_books_xlsx(tmp_path / "Books.xlsx")
    pack = build_pack_inventory([path])
    answer = answer_from_json(
        "List the named ranges from the inventory.", pack.to_json()
    )
    assert answer is not None
    assert answer.endswith("none.")
    assert "RateTable" not in answer


def test_rates_books_which_file_is_present(tmp_path: Path) -> None:
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    books = write_books_xlsx(tmp_path / "Books.xlsx")
    pack = build_pack_inventory([rates, books])
    answer = answer_inventory_question(
        "Which file does Rates read, and is it in this pack?", pack
    )
    assert answer is not None
    assert "Books.xlsx" in answer
    assert "in this pack" in answer
    assert "missing from this pack" not in answer


def test_rates_only_which_file_is_missing(tmp_path: Path) -> None:
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    pack = build_pack_inventory([rates])
    answer = answer_inventory_question(
        "Which file does Rates read, and is it in this pack?", pack
    )
    assert answer is not None
    assert "Books.xlsx" in answer
    assert "missing from this pack" in answer


def test_external_links_none_on_books(tmp_path: Path) -> None:
    path = write_books_xlsx(tmp_path / "Books.xlsx")
    pack = build_pack_inventory([path])
    answer = answer_inventory_question(
        "Are there external workbook links in the inventory?", pack
    )
    assert answer is not None
    assert answer.endswith("none.")


def test_wacc_named_ranges_list_ratetable(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    answer = answer_inventory_question(
        "List the named ranges from the inventory.", pack
    )
    assert answer is not None
    assert "RateTable" in answer
    assert "none." not in answer


def test_capped_formula_list_is_stated_not_reparsed() -> None:
    pack = PackInventory(
        files=[
            FileInventory(
                filename="big.xlsx",
                kind="xlsx",
                formulas=[
                    FormulaInfo(
                        cell="Input sheet!B35",
                        formula="='Cost of capital'!B13",
                        label="Initial cost of capital",
                    )
                ],
                formula_total=1229,
            )
        ]
    )
    answer = answer_inventory_question(
        "Where is WACC or the cost of capital computed?", pack
    )
    assert answer is not None
    assert "Input sheet!B35" in answer
    assert "1229" in answer
    assert "listed set" in answer


def test_non_lookup_question_still_builds_chat_prompt(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    question = "How is terminal value calculated?"
    assert classify_inventory_intent(question) is None
    assert answer_inventory_question(question, pack) is None
    prompt = build_chat_prompt(question, pack.to_prompt())
    assert INVENTORY_PREAMBLE in prompt
    assert "How is terminal value calculated?" in prompt
    assert "FORMULA" in prompt


def test_classify_minimum_intents() -> None:
    assert (
        classify_inventory_intent("List the named ranges from the inventory.")
        == NAMED_RANGES
    )
    assert (
        classify_inventory_intent(
            "Are there external workbook links in the inventory?"
        )
        == EXTERNAL_LINKS
    )
    assert (
        classify_inventory_intent(
            "Where is WACC or the cost of capital computed?"
        )
        == WHERE_COMPUTED
    )
    assert (
        classify_inventory_intent(
            "Which file does Rates read, and is it in this pack?"
        )
        == FILE_READS
    )
    assert classify_inventory_intent("Suggest a paste-ready FCFF formula.") is None
    assert (
        classify_inventory_intent("What does Input sheet!B35 do?") == CELL_QUOTE
    )
    assert (
        classify_inventory_intent("What does `Valuation output!C9` do?")
        == CELL_QUOTE
    )


def test_parse_cell_addresses_keeps_sheet_not_question_words() -> None:
    assert parse_cell_addresses("What does Rates!E2 do?") == ["Rates!E2"]
    assert parse_cell_addresses("What does `Input sheet!B35` do?") == [
        "Input sheet!B35"
    ]
    assert parse_cell_addresses("What does 'Cost of capital'!B13 do?") == [
        "Cost of capital!B13"
    ]
    assert parse_cell_addresses("What does Valuation output!C9 do?") == [
        "Valuation output!C9"
    ]


def test_wacc_what_does_b35_do_quotes_stored_formula(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    cached = PackInventory.from_json(pack.to_json())
    question = "What does `Input sheet!B35` do?"
    assert classify_inventory_intent(question) == CELL_QUOTE
    answer = answer_inventory_question(question, cached)
    assert answer is not None
    assert "Input sheet!B35" in answer
    assert "='Cost of capital'!B13" in answer
    assert "Initial cost of capital" in answer


def test_rates_what_does_e2_do_keeps_books_sheet(tmp_path: Path) -> None:
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    books = write_books_xlsx(tmp_path / "Books.xlsx")
    pack = build_pack_inventory([rates, books])
    answer = answer_inventory_question("What does Rates!E2 do?", pack)
    assert answer is not None
    assert "Rates!E2" in answer
    assert "=[Books.xlsx]Books!B2" in answer


def test_unknown_cell_states_cap_without_reparsing() -> None:
    pack = PackInventory(
        files=[
            FileInventory(
                filename="big.xlsx",
                kind="xlsx",
                formulas=[
                    FormulaInfo(
                        cell="Input sheet!B35",
                        formula="='Cost of capital'!B13",
                        label="Initial cost of capital",
                    )
                ],
                formula_total=1229,
            )
        ]
    )
    answer = answer_inventory_question(
        "What does Valuation output!Z99 do?", pack
    )
    assert answer is not None
    assert "Valuation output!Z99" in answer
    assert "1229" in answer
    assert "listed formulas" in answer
    assert "Input sheet!B35" not in answer
