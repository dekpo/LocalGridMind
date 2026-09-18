"""Table-facts card. Synthetic CSV only — no client files or GGUF."""

from __future__ import annotations

from pathlib import Path

from src.core.inventory import (
    MAX_SCAN_ROWS,
    PackInventory,
    build_pack_inventory,
    inspect_file,
)
from src.core.lookup import (
    TABULAR_COUNT,
    TABULAR_LARGEST,
    TABULAR_LIST,
    TABULAR_MAX_ROW,
    answer_from_json,
    answer_inventory_question,
    classify_inventory_intent,
)
from src.core.stats import build_sheet_stats, format_stat_number
from tests.workbook_fixtures import (
    write_agency_and_subagency_csv,
    write_agency_costs_csv,
    write_many_agencies_csv,
    write_wacc_pack_xlsx,
)

_LARGE_EARLY = MAX_SCAN_ROWS


def test_late_agency_is_on_card_not_just_first_sample(tmp_path: Path) -> None:
    path = write_agency_costs_csv(
        tmp_path / "agency_costs.csv",
        early_count=_LARGE_EARLY,
        late_count=40,
        late_amount=1000,
        max_row_amount=9000,
    )
    inventory = inspect_file(path)
    sheet = inventory.sheets[0]
    assert sheet.row_count == _LARGE_EARLY + 40 + 1
    assert sheet.stats is not None
    agency = next(item for item in sheet.stats.distincts if item.column == "agency")
    assert agency.count == 3
    assert "Zulu" in agency.values
    assert "Omega" in agency.values
    samples = next(column for column in sheet.columns if column.name == "agency").samples
    assert "Zulu" not in samples
    assert "Omega" not in samples


def test_group_sum_is_not_the_max_row(tmp_path: Path) -> None:
    path = write_agency_costs_csv(
        tmp_path / "agency_costs.csv",
        early_count=_LARGE_EARLY,
        late_count=40,
        late_amount=1000,
        max_row_amount=9000,
    )
    stats = inspect_file(path).sheets[0].stats
    assert stats is not None
    group = next(
        item
        for item in stats.group_sums
        if item.group_column == "agency" and item.value_column == "amount"
    )
    assert group.top[0].key == "Zulu"
    assert group.top[0].sum_value == 40_000
    max_row = next(item for item in stats.max_rows if item.value_column == "amount")
    assert max_row.value == 9000
    assert max_row.labels.get("agency") == "Omega"


def test_stats_json_roundtrip_keeps_late_agency(tmp_path: Path) -> None:
    path = write_agency_costs_csv(
        tmp_path / "agency_costs.csv",
        early_count=8,
        late_count=6,
        late_amount=1000,
        max_row_amount=4000,
    )
    pack = build_pack_inventory([path])
    restored = PackInventory.from_json(pack.to_json())
    stats = restored.files[0].sheets[0].stats
    assert stats is not None
    assert stats.row_count == 15
    agency = next(item for item in stats.distincts if item.column == "agency")
    assert "Zulu" in agency.values
    assert "Omega" in agency.values


def test_lookup_sum_winner_labelled_separately_from_max_row(
    tmp_path: Path,
) -> None:
    path = write_agency_costs_csv(
        tmp_path / "agency_costs.csv",
        early_count=8,
        late_count=6,
        late_amount=1000,
        max_row_amount=4000,
    )
    pack = PackInventory.from_json(build_pack_inventory([path]).to_json())
    question = "Which agency costs the most?"
    assert classify_inventory_intent(question) == TABULAR_LARGEST
    answer = answer_inventory_question(question, pack)
    assert answer is not None
    assert "sum of all rows" in answer
    assert "**Zulu**" in answer
    assert "6,000" in answer
    assert "Largest single row (not a total)" in answer
    assert "Omega" in answer
    assert "4,000" in answer
    assert answer.index("Zulu") < answer.index("Omega")


def test_lookup_max_row_does_not_claim_a_total(tmp_path: Path) -> None:
    path = write_agency_costs_csv(tmp_path / "agency_costs.csv")
    pack = build_pack_inventory([path])
    question = "What is the largest single row?"
    assert classify_inventory_intent(question) == TABULAR_MAX_ROW
    answer = answer_from_json(question, pack.to_json())
    assert answer is not None
    assert "not a total" in answer
    assert "Omega" in answer
    assert "Zulu" not in answer or "sum" not in answer.lower()


def test_lookup_lists_late_agencies_and_full_row_count(tmp_path: Path) -> None:
    path = write_agency_costs_csv(
        tmp_path / "agency_costs.csv",
        early_count=_LARGE_EARLY,
        late_count=40,
        late_amount=1000,
        max_row_amount=9000,
    )
    pack = build_pack_inventory([path])
    listed = answer_inventory_question("List the agencies", pack)
    assert listed is not None
    assert "Zulu" in listed
    assert "Omega" in listed
    assert classify_inventory_intent("How many rows are in the file?") == TABULAR_COUNT
    counted = answer_inventory_question("How many rows are in the file?", pack)
    assert counted is not None
    assert f"{_LARGE_EARLY + 41:,}" in counted
    agencies = answer_inventory_question("How many agencies", pack)
    assert agencies is not None
    assert "3 values" in agencies


def test_lookup_min_max_sum_and_year_range(tmp_path: Path) -> None:
    path = write_agency_costs_csv(
        tmp_path / "agency_costs.csv",
        early_count=8,
        late_count=6,
        late_amount=1000,
        max_row_amount=4000,
    )
    pack = build_pack_inventory([path])
    total = answer_inventory_question("What is the sum of amount?", pack)
    assert total is not None
    assert "10,008" in total
    assert "all rows" in total
    minimum = answer_inventory_question("What is the min of amount?", pack)
    assert minimum is not None
    assert "1" in minimum
    maximum = answer_inventory_question("What is the max of amount?", pack)
    assert maximum is not None
    assert "4,000" in maximum
    years = answer_inventory_question("What are the years", pack)
    assert years is not None
    assert "2010" in years
    assert "2021" in years


def test_unknown_column_fails_closed(tmp_path: Path) -> None:
    path = write_agency_costs_csv(tmp_path / "agency_costs.csv")
    pack = build_pack_inventory([path])
    answer = answer_inventory_question("Which country costs the most?", pack)
    assert answer is not None
    assert answer.startswith("That table fact is not on the inventory stats card.")
    assert "Available columns:" in answer
    assert "agency" in answer
    assert "amount" in answer
    assert "year" in answer
    listed = answer_inventory_question("List the countries", pack)
    assert listed is not None
    assert listed.startswith("That table fact is not on the inventory stats card.")
    assert "Available columns: " in listed
    assert listed.endswith(".")


def test_excel_without_stats_card_asks_for_csv(tmp_path: Path) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    pack = build_pack_inventory([path])
    answer = answer_inventory_question("Which agency costs the most?", pack)
    assert answer is not None
    assert answer.startswith("That table fact is not on the inventory stats card.")
    assert "please attach the table as a CSV." in answer
    assert "which group is largest" in answer


def test_forty_eight_agencies_all_listed(tmp_path: Path) -> None:
    path = write_many_agencies_csv(tmp_path / "agencies.csv", count=48)
    pack = build_pack_inventory([path])
    stats = pack.files[0].sheets[0].stats
    assert stats is not None
    agency = next(item for item in stats.distincts if item.column == "agency")
    assert agency.count == 48
    assert "Agency_01" in agency.values
    assert "Agency_48" in agency.values
    answer = answer_inventory_question("List the agencies", pack)
    assert answer is not None
    assert "Agency_01" in answer
    assert "Agency_48" in answer
    largest = answer_inventory_question("Which agency costs the most?", pack)
    assert largest is not None
    assert "Agency_48" in largest


def test_list_agencies_prefers_agency_over_sub_agency(tmp_path: Path) -> None:
    path = write_agency_and_subagency_csv(tmp_path / "split.csv")
    pack = build_pack_inventory([path])
    listed = answer_inventory_question("List the agencies", pack)
    assert listed is not None
    assert "stats card" not in listed
    assert "Alpha" in listed
    assert "Zulu" in listed
    assert "Omega" in listed
    subs = answer_inventory_question("List the sub agencies", pack)
    assert subs is not None
    assert "Alpha-1" in subs
    assert "Zulu-1" in subs


def test_money_sum_uses_grouped_decimals_not_scientific() -> None:
    assert format_stat_number(107140256588.92) == "107,140,256,588.92"
    assert format_stat_number(8503612000) == "8,503,612,000"


def test_build_sheet_stats_ignores_a_head_sample() -> None:
    import pandas as pd

    early = pd.DataFrame(
        {"agency": ["Alpha"] * 20, "amount": [1] * 20, "year": [2010] * 20}
    )
    late = pd.DataFrame(
        {
            "agency": ["Zulu"] * 5 + ["Omega"],
            "amount": [1000] * 5 + [4000],
            "year": [2020] * 5 + [2021],
        }
    )
    full = pd.concat([early, late], ignore_index=True)
    sample = build_sheet_stats(full.head(20))
    complete = build_sheet_stats(full)
    assert sample is not None and complete is not None
    sample_names = next(item for item in sample.distincts if item.column == "agency")
    full_names = next(item for item in complete.distincts if item.column == "agency")
    assert "Zulu" not in sample_names.values
    assert "Zulu" in full_names.values
    assert classify_inventory_intent("List the agencies") == TABULAR_LIST
