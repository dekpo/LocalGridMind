"""Deterministic inventory answers. The GGUF does not retrieve these facts."""

from __future__ import annotations

import re
from pathlib import Path

from .inventory import (
    FormulaInfo,
    PackInventory,
    SheetInfo,
    cell_address_key,
    indexed_formulas,
    parse_cell_addresses,
    uses_full_formula_index,
)
from .stats import (
    GroupSumStat,
    MaxRowStat,
    NumericStat,
    SheetStats,
    column_tokens,
    format_stat_number,
    match_named_column,
)

NAMED_RANGES = "named_ranges"
EXTERNAL_LINKS = "external_links"
WHERE_COMPUTED = "where_computed"
FILE_READS = "file_reads"
CELL_QUOTE = "cell_quote"
TABULAR_COUNT = "tabular_count"
TABULAR_LIST = "tabular_list"
TABULAR_AGG = "tabular_agg"
TABULAR_LARGEST = "tabular_largest"
TABULAR_MAX_ROW = "tabular_max_row"

_NAMED = re.compile(r"\bnamed\s+ranges?\b", re.I)
_EXTERNAL = re.compile(
    r"\bexternal\s+(?:workbook\s+)?links?\b|\bworkbook\s+links?\b",
    re.I,
)
_FILE_READS = re.compile(
    r"\b(?:which|what)\s+file\s+does\s+(.+?)\s+read\b",
    re.I,
)
_WHERE = re.compile(r"\bwhere\s+(?:is|are)\b", re.I)
_WHERE_TOPIC = re.compile(
    r"\bwhere\s+(?:is|are)\s+(.+?)(?:\s+(?:computed|calculated|from|"
    r"in\s+the\s+inventory))?\s*\??\s*$",
    re.I,
)
_WACC_TERMS = ("wacc", "cost of capital")
MAX_WHERE_HITS = 12
_VAGUE_TOPICS = frozenset(
    {"it", "this", "that", "they", "them", "the formula", "the value"}
)
_TABULAR_MAX_ROW = re.compile(
    r"\b(?:largest|highest|biggest|maximum)\s+(?:single\s+)?"
    r"(?:row|line|entry|record|transaction)\b"
    r"|\bsingle\s+(?:largest|highest|biggest)\b"
    r"|\b(?:which|what)\s+(?:row|line|record)\b"
    r"|\bmax(?:imum)?\s+row\b",
    re.I,
)
_TABULAR_LARGEST = re.compile(
    r"\b(?:which|what)\s+(?P<group>.+?)\s+"
    r"(?:cost[s]?|spend[s]?|ha[sve]|is|are)\s+(?:the\s+)?"
    r"(?:most|largest|highest|biggest|greatest)\b",
    re.I,
)
_TABULAR_AGG = re.compile(
    r"\b(?:what\s+is\s+)?(?:the\s+)?"
    r"(?P<kind>min(?:imum)?|max(?:imum)?|sum|total)\s+"
    r"(?:of\s+)?(?:the\s+)?(?P<col>.+?)\s*\??\s*$"
    r"|\bhow\s+much\s+(?:is\s+)?(?:the\s+)?(?:total|sum)\b",
    re.I,
)
_TABULAR_COUNT = re.compile(
    r"\bhow\s+many\b|\b(?:row\s+)?count\b|\bnumber\s+of\s+rows\b",
    re.I,
)
_TABULAR_LIST = re.compile(
    r"^\s*(?:please\s+)?(?:list|show)\s+(?:me\s+)?(?:the\s+)?"
    r"(?:unique\s+|distinct\s+)?(?P<list>.+?)"
    r"(?:\s+values?|\s+names?)?\s*\??\s*$"
    r"|^\s*what\s+are\s+(?:the\s+)?(?:unique\s+|distinct\s+)?"
    r"(?P<what>.+?)\s*\??\s*$"
    r"|^\s*which\s+(?P<which>.+?)\s+(?:are\s+there|exist|appear)\b",
    re.I,
)
_TABULAR_YEAR = re.compile(r"\byears?\b|\byear\s+range\b", re.I)
_ROW_WORDS = frozenset(
    {"row", "rows", "record", "records", "line", "lines", "entry", "entries"}
)
_CLOSED = "That table fact is not on the inventory stats card."
_CLOSED_NEED_CSV = (
    "That table fact is not on the inventory stats card.\n"
    "For totals, counts, and “which group is largest” on the data itself, "
    "please attach the table as a CSV."
)


def classify_inventory_intent(question: str) -> str | None:
    """Return a lookup intent, or None so the chat can still call the model."""
    text = question.strip()
    if not text:
        return None
    if _FILE_READS.search(text):
        return FILE_READS
    if _NAMED.search(text):
        return NAMED_RANGES
    if _EXTERNAL.search(text):
        return EXTERNAL_LINKS
    if _WHERE.search(text):
        topic = _where_topic(text)
        if topic is None and not _has_wacc_terms(text):
            return None
        return WHERE_COMPUTED
    if parse_cell_addresses(text):
        return CELL_QUOTE
    if _TABULAR_MAX_ROW.search(text):
        return TABULAR_MAX_ROW
    if _TABULAR_LARGEST.search(text):
        return TABULAR_LARGEST
    if _TABULAR_AGG.search(text):
        return TABULAR_AGG
    if _TABULAR_COUNT.search(text):
        return TABULAR_COUNT
    if _TABULAR_LIST.match(text):
        return TABULAR_LIST
    return None


def answer_inventory_question(
    question: str, pack: PackInventory
) -> str | None:
    """English fact answer from the cached pack, or None if not a lookup."""
    intent = classify_inventory_intent(question)
    if intent is None:
        return None
    if intent == NAMED_RANGES:
        return _answer_named_ranges(pack)
    if intent == EXTERNAL_LINKS:
        return _answer_external_links(pack)
    if intent == FILE_READS:
        return _answer_file_reads(question, pack)
    if intent == WHERE_COMPUTED:
        return _answer_where_computed(question, pack)
    if intent == CELL_QUOTE:
        return _answer_cell_quote(question, pack)
    if intent == TABULAR_COUNT:
        return _answer_tabular_count(question, pack)
    if intent == TABULAR_LIST:
        return _answer_tabular_list(question, pack)
    if intent == TABULAR_AGG:
        return _answer_tabular_agg(question, pack)
    if intent == TABULAR_LARGEST:
        return _answer_tabular_largest(question, pack)
    if intent == TABULAR_MAX_ROW:
        return _answer_tabular_max_row(question, pack)
    return None


def answer_from_json(question: str, inventory_json: str) -> str | None:
    """Lookup against persisted JSON. Never re-parse workbook files."""
    pack = PackInventory.from_json(inventory_json)
    return answer_inventory_question(question, pack)


def _answer_named_ranges(pack: PackInventory) -> str:
    rows: list[str] = []
    for item in pack.files:
        prefix = f"{item.filename} " if len(pack.files) > 1 else ""
        for named in item.named_ranges:
            rows.append(f"- {prefix}{named.name} → `{named.refers_to}`")
    if not rows:
        return "Named ranges in this inventory: none."
    return "Named ranges in this inventory:\n" + "\n".join(rows)


def _answer_external_links(pack: PackInventory) -> str:
    rows = _link_rows(pack)
    if not rows:
        return "External workbook links in this inventory: none."
    return "External workbook links in this inventory:\n" + "\n".join(rows)


def _link_rows(pack: PackInventory, filename: str | None = None) -> list[str]:
    rows: list[str] = []
    needle = filename.lower() if filename else None
    for item in pack.files:
        if needle is not None and not _file_matches(item.filename, needle):
            continue
        for link in item.links:
            state = (
                "in this pack" if link.present_in_pack else "missing from this pack"
            )
            rows.append(
                f"- `{link.used_in}` reads **{link.workbook}** ({state})"
            )
    return rows


def _answer_file_reads(question: str, pack: PackInventory) -> str:
    match = _FILE_READS.search(question)
    raw = (match.group(1) if match else "").strip().strip("\"'")
    token = Path(raw.replace("\\", "/")).name or raw
    if not token:
        return "No file in this question matches a workbook in this pack."
    found = None
    for item in pack.files:
        if _file_matches(item.filename, token):
            found = item
            break
    if found is None:
        return f"No file named {token} is in this pack."
    rows = _link_rows(pack, found.filename)
    if not rows:
        return (
            f"{found.filename} does not read another workbook in this inventory."
        )
    if len(rows) == 1 and found.links:
        link = found.links[0]
        state = "in this pack" if link.present_in_pack else "missing from this pack"
        return (
            f"{found.filename} reads **{link.workbook}** from `{link.used_in}`. "
            f"That file is {state}."
        )
    return f"{found.filename} reads these workbooks:\n" + "\n".join(rows)


def _answer_where_computed(question: str, pack: PackInventory) -> str:
    terms = _search_terms(question)
    listed, total = _formula_counts(pack)
    matches: list[tuple[str, FormulaInfo]] = []
    seen: set[str] = set()
    multi = len(pack.files) > 1
    for item in pack.files:
        prefix = f"{item.filename} " if multi else ""
        for formula in indexed_formulas(item):
            if not _formula_matches(formula, terms):
                continue
            key = f"{prefix}{formula.cell}"
            if key in seen:
                continue
            seen.add(key)
            matches.append((prefix, formula))
    topic = _topic_label(terms)
    if not matches:
        if not uses_full_formula_index(pack) and total > listed:
            return (
                f"{topic} is not in the listed formulas "
                f"({listed} of {total})."
            )
        return f"{topic} is not in the inventory."
    ranked = sorted(
        matches, key=lambda pair: _where_sort_key(pair[1], terms)
    )
    shown = ranked[:MAX_WHERE_HITS]
    lines = [f"These stored formulas match {topic}:"]
    for prefix, formula in shown:
        label = f" — {formula.label}" if formula.label else ""
        lines.append(
            f"- `{prefix}{formula.cell}`: `{formula.formula}`{label}"
        )
    text = "\n".join(lines)
    if len(ranked) > MAX_WHERE_HITS:
        text += (
            f"\n\nShowing {len(shown)} of {len(ranked)} matching stored formulas."
        )
    elif not uses_full_formula_index(pack) and total > listed:
        text += (
            f"\n\nThe inventory lists {listed} of {total} stored formulas. "
            "These matches are from that listed set."
        )
    return text


def _answer_cell_quote(question: str, pack: PackInventory) -> str:
    addresses = parse_cell_addresses(question)
    listed, total = _formula_counts(pack)
    index = _formulas_by_cell(pack)
    quoted: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for address in addresses:
        matches = index.get(cell_address_key(address), [])
        if not matches:
            missing.append(address)
            continue
        for prefix, formula in matches:
            key = f"{prefix}{formula.cell}"
            if key in seen:
                continue
            seen.add(key)
            label = f" — {formula.label}" if formula.label else ""
            quoted.append(f"`{prefix}{formula.cell}`: `{formula.formula}`{label}")
    parts: list[str] = []
    if quoted:
        if len(quoted) == 1:
            parts.append(quoted[0])
        else:
            parts.append("These stored formulas match the cells in your question:")
            parts.extend(f"- {line}" for line in quoted)
    for address in missing:
        if not uses_full_formula_index(pack) and total > listed:
            parts.append(
                f"`{address}` is not in the listed formulas ({listed} of {total})."
            )
        else:
            parts.append(f"`{address}` is not in the inventory.")
    return "\n\n".join(parts)


def _formulas_by_cell(
    pack: PackInventory,
) -> dict[str, list[tuple[str, FormulaInfo]]]:
    index: dict[str, list[tuple[str, FormulaInfo]]] = {}
    multi = len(pack.files) > 1
    for item in pack.files:
        prefix = f"{item.filename} " if multi else ""
        for formula in indexed_formulas(item):
            index.setdefault(cell_address_key(formula.cell), []).append(
                (prefix, formula)
            )
    return index


def _search_terms(question: str) -> tuple[str, ...]:
    if _has_wacc_terms(question):
        return _WACC_TERMS
    topic = _where_topic(question) or ""
    cleaned = " ".join(topic.split()).strip(" ?.,;:")
    if not cleaned or cleaned.lower() in _VAGUE_TOPICS:
        return ()
    return (cleaned.lower(),)


def _where_topic(question: str) -> str | None:
    match = _WHERE_TOPIC.search(question.strip())
    if not match:
        return None
    topic = " ".join(match.group(1).split()).strip(" ?.,;:")
    if not topic or topic.lower() in _VAGUE_TOPICS:
        return None
    return topic


def _topic_label(terms: tuple[str, ...]) -> str:
    if terms == _WACC_TERMS:
        return "WACC / cost of capital"
    if not terms:
        return "That item"
    return terms[0]


def _has_wacc_terms(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _WACC_TERMS)


def _formula_matches(formula: FormulaInfo, terms: tuple[str, ...]) -> bool:
    """Match label or header only. Do not treat the sheet name as a hit."""
    if not terms:
        return False
    extra = " ".join(
        part.lower()
        for part in (formula.label, formula.column_header)
        if part
    )
    formula_l = formula.formula.lower()
    for term in terms:
        if term in extra:
            return True
        if term == "wacc" and term in formula_l:
            return True
    return False


def _where_sort_key(
    formula: FormulaInfo, terms: tuple[str, ...]
) -> tuple[int, int, str]:
    """Prefer definition-style labels and column B. Stable by cell address."""
    label = (formula.label or "").lower()
    header = (formula.column_header or "").lower()
    col = _column_letter(formula.cell)
    col_rank = 0 if col == "B" else 1 if col == "C" else 2
    if terms == _WACC_TERMS:
        if "wacc" in label:
            bucket = 0
        elif label.startswith("initial cost of capital"):
            bucket = 1
        elif label.startswith("cost of capital"):
            bucket = 2
        elif "cost of capital" in label and col == "B":
            bucket = 3
        elif "cost of capital" in label:
            bucket = 4
        elif "wacc" in header or "cost of capital" in header:
            bucket = 5
        else:
            bucket = 6
    else:
        term = terms[0] if terms else ""
        if term and label.startswith(term):
            bucket = 1
        elif term and term in label:
            bucket = 2
        elif term and term in header:
            bucket = 3
        else:
            bucket = 4
    return (bucket, col_rank, formula.cell.casefold())


def _column_letter(cell: str) -> str:
    addr = str(cell).rsplit("!", 1)[-1]
    return "".join(ch for ch in addr if ch.isalpha()).upper()


def _formula_counts(pack: PackInventory) -> tuple[int, int]:
    listed = 0
    total = 0
    for item in pack.files:
        listed += len(item.formulas)
        total += item.formula_total or len(item.formulas)
    return listed, total


def _file_matches(filename: str, token: str) -> bool:
    name = Path(filename.replace("\\", "/")).name.lower()
    stem = Path(name).stem.lower()
    needle = Path(token.replace("\\", "/")).name.lower()
    needle_stem = Path(needle).stem.lower()
    return name == needle or stem == needle or stem == needle_stem


def _iter_sheet_stats(
    pack: PackInventory,
) -> list[tuple[str, SheetInfo, SheetStats]]:
    rows: list[tuple[str, SheetInfo, SheetStats]] = []
    multi = len(pack.files) > 1
    for item in pack.files:
        prefix = f"{item.filename} " if multi else ""
        for sheet in item.sheets:
            if sheet.stats is None:
                continue
            rows.append((prefix, sheet, sheet.stats))
    return rows


def _card_column_names(stats: SheetStats) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for name in (
        [item.column for item in stats.distincts]
        + [item.column for item in stats.numerics]
        + [item.column for item in stats.year_ranges]
    ):
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    return ordered


def _closed_missing_column(
    cards: list[tuple[str, SheetInfo, SheetStats]],
) -> str:
    listed = _available_columns_line(cards)
    if not listed:
        return _CLOSED
    return f"{_CLOSED}\n{listed}"


def _available_columns_line(
    cards: list[tuple[str, SheetInfo, SheetStats]],
) -> str:
    if len(cards) == 1:
        names = _card_column_names(cards[0][2])
        if not names:
            return ""
        return "Available columns: " + ", ".join(names) + "."
    lines = ["Available columns:"]
    for prefix, sheet, stats in cards:
        names = _card_column_names(stats)
        if not names:
            continue
        lines.append(f"- {prefix}{sheet.name}: {', '.join(names)}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _answer_tabular_count(question: str, pack: PackInventory) -> str:
    cards = _iter_sheet_stats(pack)
    if not cards:
        return _CLOSED_NEED_CSV
    topic = _count_topic(question)
    if _is_row_topic(topic):
        if len(cards) == 1:
            _prefix, sheet, stats = cards[0]
            return (
                f"{sheet.name} has {stats.row_count:,} data rows "
                "in the inventory table facts."
            )
        lines = ["Row counts in the inventory table facts:"]
        for prefix, sheet, stats in cards:
            lines.append(f"- {prefix}{sheet.name}: {stats.row_count:,} data rows")
        return "\n".join(lines)
    if _TABULAR_YEAR.search(topic):
        years = _collect_year_answers(cards, topic)
        return years if years is not None else _closed_missing_column(cards)
    matches: list[str] = []
    for prefix, sheet, stats in cards:
        column = match_named_column(topic, [item.column for item in stats.distincts])
        if column is None:
            continue
        distinct = next(item for item in stats.distincts if item.column == column)
        matches.append(
            f"{prefix}{sheet.name} / {distinct.column}: {distinct.count} values"
        )
    if not matches:
        return _closed_missing_column(cards)
    if len(matches) == 1:
        return f"{matches[0]} in the inventory table facts."
    return "Counts in the inventory table facts:\n" + "\n".join(
        f"- {item}" for item in matches
    )


def _answer_tabular_list(question: str, pack: PackInventory) -> str:
    cards = _iter_sheet_stats(pack)
    if not cards:
        return _CLOSED_NEED_CSV
    topic = _list_topic(question)
    if not topic:
        return _closed_missing_column(cards)
    if _TABULAR_YEAR.search(topic):
        years = _collect_year_answers(cards, topic)
        return years if years is not None else _closed_missing_column(cards)
    matches: list[str] = []
    for prefix, sheet, stats in cards:
        column = match_named_column(topic, [item.column for item in stats.distincts])
        if column is None:
            continue
        distinct = next(item for item in stats.distincts if item.column == column)
        listed = ", ".join(distinct.values) if distinct.values else "none listed"
        matches.append(
            f"{prefix}{sheet.name} / {distinct.column} "
            f"({distinct.count}): {listed}"
        )
    if not matches:
        return _closed_missing_column(cards)
    if len(matches) == 1:
        return matches[0] + "."
    return "Values in the inventory table facts:\n" + "\n".join(
        f"- {item}" for item in matches
    )


def _answer_tabular_agg(question: str, pack: PackInventory) -> str:
    cards = _iter_sheet_stats(pack)
    if not cards:
        return _CLOSED_NEED_CSV
    kind, topic = _agg_parts(question)
    if _TABULAR_YEAR.search(question) or (topic and _TABULAR_YEAR.search(topic)):
        years = _collect_year_answers(cards, topic or "year")
        return years if years is not None else _closed_missing_column(cards)
    numeric = _pick_numeric(cards, topic)
    if numeric is None:
        return _closed_missing_column(cards)
    prefix, sheet, stat = numeric
    loc = f"{prefix}{sheet.name} / {stat.column}"
    if kind in {"min", "minimum"}:
        return f"{loc} minimum: {format_stat_number(stat.min_value)}."
    if kind in {"max", "maximum"}:
        return f"{loc} maximum: {format_stat_number(stat.max_value)}."
    return f"{loc} sum (all rows): {format_stat_number(stat.sum_value)}."


def _answer_tabular_largest(question: str, pack: PackInventory) -> str:
    cards = _iter_sheet_stats(pack)
    if not cards:
        return _CLOSED_NEED_CSV
    group_hint = _largest_group_hint(question)
    combo = _pick_group_sum(cards, group_hint, question)
    if combo is None:
        return _closed_missing_column(cards)
    prefix, sheet, group = combo
    if not group.top:
        return _closed_missing_column(cards)
    winner = group.top[0]
    loc = f"{prefix}{sheet.name}"
    lines = [
        f"Largest total {group.value_column} by {group.group_column} "
        f"(sum of all rows) in {loc}: **{winner.key}** — "
        f"{format_stat_number(winner.sum_value)}."
    ]
    max_row = _matching_max_row(cards, group.value_column, prefix, sheet.name)
    if max_row is not None:
        lines.append(_max_row_sentence(max_row[0], max_row[1], max_row[2]))
    return "\n\n".join(lines)


def _answer_tabular_max_row(question: str, pack: PackInventory) -> str:
    cards = _iter_sheet_stats(pack)
    if not cards:
        return _CLOSED_NEED_CSV
    topic = _max_row_value_hint(question)
    picked = _pick_max_row(cards, topic)
    if picked is None:
        return _closed_missing_column(cards)
    prefix, sheet, row = picked
    return _max_row_sentence(prefix, sheet, row)


def _max_row_sentence(prefix: str, sheet: SheetInfo, row: MaxRowStat) -> str:
    labels = ""
    if row.labels:
        bits = [f"{key} {value}" for key, value in row.labels.items()]
        labels = " (" + ", ".join(bits) + ")"
    return (
        f"Largest single row (not a total) in {prefix}{sheet.name}: "
        f"{row.value_column} {format_stat_number(row.value)}{labels}."
    )


def _is_row_topic(topic: str | None) -> bool:
    if not topic:
        return True
    tokens = column_tokens(topic)
    return bool(tokens & _ROW_WORDS)


def _count_topic(question: str) -> str | None:
    match = re.search(
        r"\bhow\s+many\s+(?:data\s+)?(?P<col>.+?)\s*\??\s*$",
        question.strip(),
        re.I,
    )
    if not match:
        return None
    topic = _clean_topic(match.group("col"))
    return topic or None


def _list_topic(question: str) -> str | None:
    match = _TABULAR_LIST.match(question.strip())
    if not match:
        return None
    raw = match.group("list") or match.group("what") or match.group("which") or ""
    return _clean_topic(raw)


def _agg_parts(question: str) -> tuple[str, str | None]:
    match = _TABULAR_AGG.search(question.strip())
    if not match:
        return "sum", None
    kind = (match.groupdict().get("kind") or "sum").lower()
    topic = _clean_topic(match.groupdict().get("col") or "")
    return kind, topic or None


def _largest_group_hint(question: str) -> str | None:
    match = _TABULAR_LARGEST.search(question.strip())
    if not match:
        return None
    return _clean_topic(match.group("group"))


def _max_row_value_hint(question: str) -> str | None:
    match = re.search(
        r"\b(?:largest|highest|biggest|maximum)\s+(?:single\s+)?"
        r"(?:row|line|entry|record|transaction)\s+"
        r"(?:of|for|in)?\s*(?:the\s+)?(?P<col>.+?)\s*\??\s*$",
        question.strip(),
        re.I,
    )
    if not match:
        return None
    topic = _clean_topic(match.group("col"))
    return topic or None


def _clean_topic(raw: str) -> str:
    text = " ".join(str(raw or "").split()).strip(" ?.,;:")
    text = re.sub(
        r"\b(?:from|in)\s+(?:the\s+)?(?:inventory|file|sheet|table|data)\b",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b(?:values?|names?|there|exist|appear|unique|distinct)\b",
        "",
        text,
        flags=re.I,
    )
    return " ".join(text.split()).strip(" ?.,;:")


def _collect_year_answers(
    cards: list[tuple[str, SheetInfo, SheetStats]], topic: str
) -> str | None:
    lines: list[str] = []
    for prefix, sheet, stats in cards:
        names = [item.column for item in stats.year_ranges]
        column = match_named_column(topic, names) if names else None
        chosen = stats.year_ranges
        if column is not None:
            chosen = [item for item in stats.year_ranges if item.column == column]
        elif len(stats.year_ranges) != 1 and topic not in {"year", "years"}:
            continue
        for item in chosen:
            lines.append(
                f"{prefix}{sheet.name} / {item.column}: "
                f"{item.min_year}–{item.max_year}"
            )
    if not lines:
        return None
    if len(lines) == 1:
        return f"Year range in the inventory table facts: {lines[0]}."
    return "Year ranges in the inventory table facts:\n" + "\n".join(
        f"- {item}" for item in lines
    )


def _pick_numeric(
    cards: list[tuple[str, SheetInfo, SheetStats]], topic: str | None
) -> tuple[str, SheetInfo, NumericStat] | None:
    candidates: list[tuple[str, SheetInfo, NumericStat]] = []
    for prefix, sheet, stats in cards:
        names = [item.column for item in stats.numerics]
        if topic:
            column = match_named_column(topic, names)
            if column is None:
                continue
            stat = next(item for item in stats.numerics if item.column == column)
            candidates.append((prefix, sheet, stat))
            continue
        if len(stats.numerics) == 1:
            candidates.append((prefix, sheet, stats.numerics[0]))
    if len(candidates) == 1:
        return candidates[0]
    return None


def _pick_group_sum(
    cards: list[tuple[str, SheetInfo, SheetStats]],
    group_hint: str | None,
    question: str,
) -> tuple[str, SheetInfo, GroupSumStat] | None:
    value_hint = _value_hint_from_question(question)
    candidates: list[tuple[str, SheetInfo, GroupSumStat]] = []
    for prefix, sheet, stats in cards:
        groups = stats.group_sums
        if group_hint:
            column = match_named_column(
                group_hint, [item.group_column for item in groups]
            )
            if column is None:
                continue
            groups = [item for item in groups if item.group_column == column]
        if value_hint:
            column = match_named_column(
                value_hint, [item.value_column for item in groups]
            )
            if column is not None:
                groups = [item for item in groups if item.value_column == column]
        if len(groups) == 1:
            candidates.append((prefix, sheet, groups[0]))
        elif not group_hint and not value_hint and len(stats.group_sums) == 1:
            candidates.append((prefix, sheet, stats.group_sums[0]))
    if len(candidates) == 1:
        return candidates[0]
    return None


def _pick_max_row(
    cards: list[tuple[str, SheetInfo, SheetStats]], topic: str | None
) -> tuple[str, SheetInfo, MaxRowStat] | None:
    candidates: list[tuple[str, SheetInfo, MaxRowStat]] = []
    for prefix, sheet, stats in cards:
        rows = stats.max_rows
        if topic:
            column = match_named_column(topic, [item.value_column for item in rows])
            if column is None:
                continue
            rows = [item for item in rows if item.value_column == column]
        if len(rows) == 1:
            candidates.append((prefix, sheet, rows[0]))
    if len(candidates) == 1:
        return candidates[0]
    return None


def _matching_max_row(
    cards: list[tuple[str, SheetInfo, SheetStats]],
    value_column: str,
    prefix: str,
    sheet_name: str,
) -> tuple[str, SheetInfo, MaxRowStat] | None:
    for item_prefix, sheet, stats in cards:
        if item_prefix != prefix or sheet.name != sheet_name:
            continue
        for row in stats.max_rows:
            if row.value_column == value_column:
                return item_prefix, sheet, row
    return None


def _value_hint_from_question(question: str) -> str | None:
    tokens = column_tokens(question)
    hints = {
        "amount",
        "cost",
        "costs",
        "revenue",
        "spend",
        "spending",
        "value",
        "total",
        "expense",
        "income",
        "rate",
    }
    overlap = tokens & hints
    if len(overlap) == 1:
        return next(iter(overlap))
    return None
