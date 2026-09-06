"""Deterministic inventory answers. The GGUF does not retrieve these facts."""

from __future__ import annotations

import re
from pathlib import Path

from .inventory import FormulaInfo, PackInventory

NAMED_RANGES = "named_ranges"
EXTERNAL_LINKS = "external_links"
WHERE_COMPUTED = "where_computed"
FILE_READS = "file_reads"

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
_VAGUE_TOPICS = frozenset(
    {"it", "this", "that", "they", "them", "the formula", "the value"}
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
        for formula in item.formulas:
            if not _formula_matches(formula, terms):
                continue
            key = f"{prefix}{formula.cell}"
            if key in seen:
                continue
            seen.add(key)
            matches.append((prefix, formula))
    topic = _topic_label(terms)
    if not matches:
        if total > listed:
            return (
                f"{topic} is not in the listed formulas "
                f"({listed} of {total})."
            )
        return f"{topic} is not in the inventory."
    lines = [f"These stored formulas match {topic}:"]
    for prefix, formula in matches:
        label = f" — {formula.label}" if formula.label else ""
        lines.append(
            f"- `{prefix}{formula.cell}`: `{formula.formula}`{label}"
        )
    text = "\n".join(lines)
    if total > listed:
        text += (
            f"\n\nThe inventory lists {listed} of {total} stored formulas. "
            "These matches are from that listed set."
        )
    return text


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
    """Match label, header, or cell. Formula text only for a bare WACC token."""
    if not terms:
        return False
    extra = " ".join(
        part.lower()
        for part in (formula.cell, formula.label, formula.column_header)
        if part
    )
    formula_l = formula.formula.lower()
    for term in terms:
        if term in extra:
            return True
        if term == "wacc" and term in formula_l:
            return True
    return False


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
