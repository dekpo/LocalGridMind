"""Compact table-facts card. Built once from the full frame, never from a sample."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

LOW_CARDINALITY_MAX = 64
TOP_GROUP_SUMS = 5
MAX_GROUP_COMBOS = 8
MAX_NUMERIC_COLUMNS = 8
MAX_DISTINCT_COLUMNS = 12
MAX_LABEL_CHARS = 48
YEAR_MIN = 1900
YEAR_MAX = 2100
NUMERIC_SHARE = 0.5
# Excel table-facts: skip formula-heavy workbooks (Ginzu / WACC models).
TABULAR_MAX_FILE_FORMULAS = 20
TABULAR_MAX_FORMULA_RATIO = 0.05
TABULAR_MIN_ROWS = 8
TABULAR_MIN_COLUMNS = 2
_ID_NAMES = frozenset(
    {"id", "ids", "index", "row", "rows", "n", "no", "num", "number", "pk"}
)
_AMOUNT_HINTS = (
    "amount",
    "cost",
    "costs",
    "revenue",
    "spend",
    "spending",
    "value",
    "total",
    "expense",
    "expenses",
    "income",
    "qty",
    "quantity",
    "rate",
)
_GROUP_HINTS = (
    "agency",
    "agencies",
    "book",
    "books",
    "category",
    "categories",
    "country",
    "countries",
    "department",
    "group",
    "groups",
    "name",
    "names",
    "region",
    "type",
    "types",
)
_YEAR_NAME = re.compile(r"\byear|date|period\b", re.I)
_FORMULA_TEXT = re.compile(r"^\s*=")


@dataclass
class DistinctStat:
    column: str
    count: int
    values: list[str] = field(default_factory=list)


@dataclass
class NumericStat:
    column: str
    min_value: float
    max_value: float
    sum_value: float
    numeric_count: int


@dataclass
class YearRangeStat:
    column: str
    min_year: int
    max_year: int


@dataclass
class GroupSumEntry:
    key: str
    sum_value: float


@dataclass
class GroupSumStat:
    group_column: str
    value_column: str
    top: list[GroupSumEntry] = field(default_factory=list)


@dataclass
class MaxRowStat:
    value_column: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class SheetStats:
    row_count: int
    distincts: list[DistinctStat] = field(default_factory=list)
    numerics: list[NumericStat] = field(default_factory=list)
    year_ranges: list[YearRangeStat] = field(default_factory=list)
    group_sums: list[GroupSumStat] = field(default_factory=list)
    max_rows: list[MaxRowStat] = field(default_factory=list)

    def any_facts(self) -> bool:
        return bool(
            self.row_count
            or self.distincts
            or self.numerics
            or self.year_ranges
            or self.group_sums
            or self.max_rows
        )


def file_allows_tabular_stats(formula_total: int) -> bool:
    """False for formula models. A couple of lookups in a data table is fine."""
    return int(formula_total or 0) <= TABULAR_MAX_FILE_FORMULAS


def sheet_looks_tabular(
    *,
    row_count: int,
    column_count: int,
    formula_count: int,
    hidden: bool = False,
) -> bool:
    """Header-style data grid, not a labeled calculator sheet."""
    if hidden:
        return False
    if row_count < TABULAR_MIN_ROWS or column_count < TABULAR_MIN_COLUMNS:
        return False
    ratio = formula_count / max(int(row_count), 1)
    return ratio <= TABULAR_MAX_FORMULA_RATIO


def build_sheet_stats(frame: pd.DataFrame) -> SheetStats | None:
    """Aggregates from every row. Do not pass a head() sample."""
    if frame is None or frame.empty:
        return None
    work = _prepare_frame(frame)
    if work.empty:
        return None
    row_count = int((~work.isna().all(axis=1)).sum())
    if row_count <= 0:
        return None

    year_ranges = _year_ranges(work)
    year_columns = {item.column for item in year_ranges}
    numerics = _numeric_stats(work, year_columns)
    numeric_names = {item.column for item in numerics}
    distincts = _distinct_stats(work, numeric_names, year_columns)
    group_sums = _group_sums(work, distincts, numerics)
    max_rows = _max_rows(work, numerics, distincts, year_ranges)
    stats = SheetStats(
        row_count=row_count,
        distincts=distincts,
        numerics=numerics,
        year_ranges=year_ranges,
        group_sums=group_sums,
        max_rows=max_rows,
    )
    return stats if stats.any_facts() else None


def stats_from_dict(data: dict[str, Any] | None) -> SheetStats | None:
    """Restore a card from pack JSON. Missing keys stay empty."""
    if not data:
        return None
    stats = SheetStats(
        row_count=int(data.get("row_count") or 0),
        distincts=[
            DistinctStat(
                column=str(item.get("column") or ""),
                count=int(item.get("count") or 0),
                values=[str(value) for value in item.get("values") or []],
            )
            for item in data.get("distincts") or []
        ],
        numerics=[
            NumericStat(
                column=str(item.get("column") or ""),
                min_value=float(item.get("min_value") or 0.0),
                max_value=float(item.get("max_value") or 0.0),
                sum_value=float(item.get("sum_value") or 0.0),
                numeric_count=int(item.get("numeric_count") or 0),
            )
            for item in data.get("numerics") or []
        ],
        year_ranges=[
            YearRangeStat(
                column=str(item.get("column") or ""),
                min_year=int(item.get("min_year") or 0),
                max_year=int(item.get("max_year") or 0),
            )
            for item in data.get("year_ranges") or []
        ],
        group_sums=[
            GroupSumStat(
                group_column=str(item.get("group_column") or ""),
                value_column=str(item.get("value_column") or ""),
                top=[
                    GroupSumEntry(
                        key=str(entry.get("key") or ""),
                        sum_value=float(entry.get("sum_value") or 0.0),
                    )
                    for entry in item.get("top") or []
                ],
            )
            for item in data.get("group_sums") or []
        ],
        max_rows=[
            MaxRowStat(
                value_column=str(item.get("value_column") or ""),
                value=float(item.get("value") or 0.0),
                labels={
                    str(key): str(value)
                    for key, value in (item.get("labels") or {}).items()
                },
            )
            for item in data.get("max_rows") or []
        ],
    )
    return stats if stats.any_facts() else None


def format_stat_number(value: float | int) -> str:
    number = float(value)
    if not math.isfinite(number):
        return "n/a"
    if abs(number - round(number)) < 1e-6 and abs(number) < 1e15:
        return f"{int(round(number)):,}"
    if abs(number) >= 1:
        return f"{number:,.2f}"
    return f"{number:,.6g}"


def english_stat_lines(stats: SheetStats) -> list[str]:
    """Analyst English. Labels sum totals separately from a single max row."""
    lines = [f"  - Table facts (all {stats.row_count:,} rows):"]
    for item in stats.distincts:
        listed = ", ".join(item.values) if item.values else ""
        extra = f" ({listed})" if listed else ""
        lines.append(f"    - {item.column}: {item.count} values{extra}")
    for item in stats.numerics:
        lines.append(
            f"    - {item.column}: min {format_stat_number(item.min_value)}; "
            f"max {format_stat_number(item.max_value)}; "
            f"sum {format_stat_number(item.sum_value)}"
        )
    for item in stats.year_ranges:
        lines.append(f"    - {item.column}: {item.min_year}–{item.max_year}")
    for item in stats.group_sums:
        lines.append(
            f"    - Largest totals (sum of all rows) by "
            f"{item.group_column} × {item.value_column}:"
        )
        for entry in item.top:
            lines.append(
                f"      - {entry.key} — {format_stat_number(entry.sum_value)}"
            )
    for item in stats.max_rows:
        labels = _label_clause(item.labels)
        lines.append(
            f"    - Largest single row (not a total): {item.value_column} "
            f"{format_stat_number(item.value)}{labels}"
        )
    return lines


def prompt_stat_lines(stats: SheetStats, *, prefix: str = "") -> list[str]:
    """Compact card for the GGUF. Counts and aggregates only — no row dump."""
    lines = [f"  {prefix}STATS rows={stats.row_count}"]
    for item in stats.distincts:
        lines.append(f"    DISTINCT {item.column} n={item.count}")
    for item in stats.numerics:
        lines.append(
            f"    NUM {item.column} min={_prompt_number(item.min_value)} "
            f"max={_prompt_number(item.max_value)} "
            f"sum={_prompt_number(item.sum_value)}"
        )
    for item in stats.year_ranges:
        lines.append(f"    YEAR {item.column} {item.min_year}-{item.max_year}")
    for item in stats.group_sums:
        bits = [
            f"{entry.key}={_prompt_number(entry.sum_value)}" for entry in item.top
        ]
        lines.append(
            f"    TOP_SUM {item.group_column}/{item.value_column} "
            + "; ".join(bits)
        )
    for item in stats.max_rows:
        labels = " ".join(
            f"{key}={value}" for key, value in item.labels.items()
        )
        extra = f" {labels}" if labels else ""
        lines.append(
            f"    MAX_ROW {item.value_column}={_prompt_number(item.value)}{extra}"
        )
    return lines


def normalize_column_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _word_stem(word: str) -> str:
    text = normalize_column_key(word)
    if " " in text:
        return text
    if text.endswith("ies") and len(text) > 4:
        return text[:-3] + "y"
    if text.endswith("es") and len(text) > 3:
        return text[:-2]
    if text.endswith("s") and len(text) > 3:
        return text[:-1]
    return text


def column_tokens(name: str) -> set[str]:
    parts = [part for part in normalize_column_key(name).split() if part]
    extras: set[str] = set()
    for part in parts:
        if part.endswith("ies") and len(part) > 4:
            extras.add(part[:-3] + "y")
        elif part.endswith("es") and len(part) > 3:
            extras.add(part[:-2])
            extras.add(part[:-1])
        elif part.endswith("s") and len(part) > 3:
            extras.add(part[:-1])
        else:
            extras.add(part + "s")
            extras.add(part + "es")
            if part.endswith("y") and len(part) > 2:
                extras.add(part[:-1] + "ies")
    return set(parts) | extras


def match_named_column(needle: str, names: list[str]) -> str | None:
    """Exact / token overlap against card columns. Fail closed if ambiguous."""
    cleaned = normalize_column_key(needle)
    if not cleaned:
        return None
    if cleaned in {"row", "rows", "record", "records", "line", "lines"}:
        return None
    exact = [name for name in names if normalize_column_key(name) == cleaned]
    if len(exact) == 1:
        return exact[0]
    tokens = column_tokens(cleaned)
    if not tokens:
        return None
    needle_stem = _word_stem(cleaned)
    synonyms = [
        name
        for name in names
        if " " not in normalize_column_key(name)
        and _word_stem(normalize_column_key(name)) == needle_stem
    ]
    if len(synonyms) == 1:
        return synonyms[0]
    scored: list[tuple[int, str]] = []
    for name in names:
        overlap = column_tokens(name) & tokens
        if overlap:
            scored.append((len(overlap), name))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1].casefold()))
    best = scored[0][0]
    winners = [name for score, name in scored if score == best]
    if len(winners) == 1:
        return winners[0]
    return None


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    cleaned.columns = [_column_label(column, index) for index, column in enumerate(cleaned.columns)]
    for column in cleaned.columns:
        cleaned[column] = [_cell_value(value) for value in cleaned[column].tolist()]
    return cleaned


def _column_label(name: Any, index: int) -> str:
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return f"Column {index + 1}"
    text = " ".join(str(name).split())
    return text or f"Column {index + 1}"


def _cell_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if _is_formula_value(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return value


def _is_formula_value(value: Any) -> bool:
    return isinstance(value, str) and bool(_FORMULA_TEXT.match(value))


def _year_ranges(frame: pd.DataFrame) -> list[YearRangeStat]:
    found: list[YearRangeStat] = []
    for column in frame.columns:
        years = _years_in_series(frame[column], str(column))
        if years is None or years.empty:
            continue
        found.append(
            YearRangeStat(
                column=str(column),
                min_year=int(years.min()),
                max_year=int(years.max()),
            )
        )
    return found


def _years_in_series(series: pd.Series, column: str) -> pd.Series | None:
    name_looks_year = bool(_YEAR_NAME.search(column))
    extracted = _extract_years(series)
    if extracted is None:
        return None
    filled = extracted.dropna()
    if filled.empty:
        return None
    share = len(filled) / max(1, int(series.notna().sum()))
    if name_looks_year and share >= 0.3:
        return filled.astype(int)
    if share >= 0.8:
        return filled.astype(int)
    return None


def _extract_years(series: pd.Series) -> pd.Series:
    values: list[float | None] = []
    for value in series.tolist():
        year = _value_year(value)
        values.append(float(year) if year is not None else None)
    return pd.Series(values, index=series.index, dtype="float64")


def _value_year(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, datetime):
        year = value.year
        return year if YEAR_MIN <= year <= YEAR_MAX else None
    if isinstance(value, date):
        year = value.year
        return year if YEAR_MIN <= year <= YEAR_MAX else None
    if isinstance(value, pd.Timestamp):
        year = int(value.year)
        return year if YEAR_MIN <= year <= YEAR_MAX else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer():
            year = int(value)
            return year if YEAR_MIN <= year <= YEAR_MAX else None
        return None
    text = str(value).strip()
    match = re.search(r"\b((?:19|20)\d{2})\b", text)
    if match:
        year = int(match.group(1))
        return year if YEAR_MIN <= year <= YEAR_MAX else None
    return None


def _numeric_stats(
    frame: pd.DataFrame, year_columns: set[str]
) -> list[NumericStat]:
    found: list[NumericStat] = []
    for column in frame.columns:
        name = str(column)
        if name in year_columns:
            continue
        if normalize_column_key(name) in _ID_NAMES:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        filled = numeric.dropna()
        if filled.empty:
            continue
        non_empty = int(pd.Series(frame[column]).notna().sum())
        if non_empty <= 0:
            continue
        if len(filled) / non_empty < NUMERIC_SHARE:
            continue
        tokens = column_tokens(name)
        if (
            int(filled.nunique()) == int(len(frame))
            and len(frame) > 2
            and ("id" in tokens or normalize_column_key(name) in _ID_NAMES)
        ):
            continue
        found.append(
            NumericStat(
                column=name,
                min_value=float(filled.min()),
                max_value=float(filled.max()),
                sum_value=float(filled.sum()),
                numeric_count=int(len(filled)),
            )
        )
        if len(found) >= MAX_NUMERIC_COLUMNS:
            break
    found.sort(key=lambda item: (_amount_rank(item.column), item.column.casefold()))
    return found


def _distinct_stats(
    frame: pd.DataFrame,
    numeric_names: set[str],
    year_columns: set[str],
) -> list[DistinctStat]:
    found: list[DistinctStat] = []
    for column in frame.columns:
        name = str(column)
        if name in numeric_names:
            continue
        texts = _text_values(frame[column])
        unique = sorted(set(texts), key=lambda item: item.casefold())
        count = len(unique)
        if count < 1 or count > LOW_CARDINALITY_MAX:
            continue
        if count == len(frame) and len(frame) > LOW_CARDINALITY_MAX:
            continue
        found.append(DistinctStat(column=name, count=count, values=unique))
        if len(found) >= MAX_DISTINCT_COLUMNS:
            break
    found.sort(key=lambda item: (_group_rank(item.column), item.column.casefold()))
    return found


def _text_values(series: pd.Series) -> list[str]:
    values: list[str] = []
    for value in series.tolist():
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        if isinstance(value, bool):
            values.append("true" if value else "false")
            continue
        text = _clip(" ".join(str(value).split()), MAX_LABEL_CHARS)
        if text:
            values.append(text)
    return values


def _group_sums(
    frame: pd.DataFrame,
    distincts: list[DistinctStat],
    numerics: list[NumericStat],
) -> list[GroupSumStat]:
    if not distincts or not numerics:
        return []
    groups = [item for item in distincts if 2 <= item.count <= LOW_CARDINALITY_MAX]
    pairs: list[tuple[int, DistinctStat, NumericStat]] = []
    for group in groups:
        for numeric in numerics:
            if group.column == numeric.column:
                continue
            rank = _group_rank(group.column) + _amount_rank(numeric.column)
            pairs.append((rank, group, numeric))
    pairs.sort(key=lambda item: (item[0], item[1].column.casefold(), item[2].column.casefold()))
    found: list[GroupSumStat] = []
    seen: set[tuple[str, str]] = set()
    for _rank, group, numeric in pairs:
        key = (group.column, numeric.column)
        if key in seen:
            continue
        seen.add(key)
        top = _top_group_sums(frame, group.column, numeric.column)
        if not top:
            continue
        found.append(
            GroupSumStat(
                group_column=group.column,
                value_column=numeric.column,
                top=top,
            )
        )
        if len(found) >= MAX_GROUP_COMBOS:
            break
    return found


def _top_group_sums(
    frame: pd.DataFrame, group_column: str, value_column: str
) -> list[GroupSumEntry]:
    numeric = pd.to_numeric(frame[value_column], errors="coerce")
    keys = pd.Series(
        [_clip(" ".join(str(value).split()), MAX_LABEL_CHARS) if value is not None else None
         for value in frame[group_column].tolist()],
        index=frame.index,
    )
    work = pd.DataFrame({"key": keys, "value": numeric}).dropna(subset=["key", "value"])
    if work.empty:
        return []
    grouped = work.groupby("key", sort=False)["value"].sum()
    ordered = grouped.sort_values(ascending=False)
    top = ordered.head(TOP_GROUP_SUMS)
    return [
        GroupSumEntry(key=str(key), sum_value=float(value))
        for key, value in top.items()
    ]


def _max_rows(
    frame: pd.DataFrame,
    numerics: list[NumericStat],
    distincts: list[DistinctStat],
    year_ranges: list[YearRangeStat],
) -> list[MaxRowStat]:
    label_columns = [item.column for item in distincts] + [
        item.column for item in year_ranges
    ]
    found: list[MaxRowStat] = []
    for numeric in numerics:
        series = pd.to_numeric(frame[numeric.column], errors="coerce")
        if series.dropna().empty:
            continue
        index = series.idxmax()
        labels: dict[str, str] = {}
        for column in label_columns:
            if column == numeric.column:
                continue
            raw = frame.at[index, column] if column in frame.columns else None
            if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                continue
            year = _value_year(raw)
            text = str(year) if year is not None and column in {item.column for item in year_ranges} else _clip(
                " ".join(str(raw).split()), MAX_LABEL_CHARS
            )
            if text:
                labels[column] = text
        found.append(
            MaxRowStat(
                value_column=numeric.column,
                value=float(series.loc[index]),
                labels=labels,
            )
        )
    return found


def _amount_rank(name: str) -> int:
    tokens = column_tokens(name)
    if tokens & set(_AMOUNT_HINTS):
        return 0
    return 1


def _group_rank(name: str) -> int:
    tokens = column_tokens(name)
    if tokens & set(_GROUP_HINTS):
        return 0
    return 1


def _label_clause(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    bits = [f"{key} {value}" for key, value in labels.items()]
    return " (" + ", ".join(bits) + ")"


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _prompt_number(value: float) -> str:
    number = float(value)
    if not math.isfinite(number):
        return "n/a"
    if abs(number - round(number)) < 1e-6 and abs(number) < 1e15:
        return str(int(round(number)))
    if abs(number) >= 1:
        return f"{number:.2f}"
    return f"{number:.6g}"
