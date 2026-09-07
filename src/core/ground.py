"""Compare a model reply to listed cell formulas. Never invent numbers."""

from __future__ import annotations

import re

from .inventory import (
    FormulaInfo,
    PackInventory,
    cell_address_key,
    iter_sheet_cells,
)

_SEP = re.compile(
    r"^(?:stores\b|stored(?:\s+as)?\b|equals\b|equal(?:\s+to)?\b|\bas\b|:|\bis\b)\s*",
    re.I,
)
_FORMULA_BODY = re.compile(
    r"=\s*[\w+\-*/()\[\],'.!_:$%^&<>]+(?:\s*[\w+\-*/()\[\],'.!_:$%^&<>]+)*",
    re.I,
)
_BARE_EXPR = re.compile(
    r"[A-Za-z]{1,3}\d+(?:\s*[+\-*/]\s*[A-Za-z]{1,3}\d+)+",
    re.I,
)
_BARE_A1 = re.compile(r"(?<![A-Za-z0-9_.'])\$?([A-Za-z]{1,3})\$?(\d+)\b")


def ground_model_reply(text: str, pack: PackInventory) -> str:
    """Append a short correction when the reply mis-states a listed formula."""
    mismatches = _formula_mismatches(text, pack)
    if not mismatches:
        return text
    notes = [
        _correction_line(prefix, formula, claimed)
        for prefix, formula, claimed in mismatches
    ]
    if len(notes) == 1:
        return f"{text.rstrip()}\n\n{notes[0]}"
    bullets = "\n".join(f"- {note}" for note in notes)
    return (
        f"{text.rstrip()}\n\n"
        "The workbook inventory lists different stored formulas:\n"
        f"{bullets}"
    )


def ground_from_json(text: str, inventory_json: str) -> str:
    """Same check against persisted JSON. Do not re-parse workbook files."""
    return ground_model_reply(text, PackInventory.from_json(inventory_json))


def _correction_line(prefix: str, formula: FormulaInfo, claimed: str) -> str:
    return (
        f"The stored formula for `{prefix}{formula.cell}` is "
        f"`{formula.formula}`, not `{claimed}`."
    )


def _formula_mismatches(
    text: str, pack: PackInventory
) -> list[tuple[str, FormulaInfo, str]]:
    by_full, by_a1 = _listed_indexes(pack)
    found: list[tuple[str, FormulaInfo, str]] = []
    seen: set[str] = set()
    for _start, end, sheet, a1 in _cell_mentions(text):
        claimed = _read_formula(text[end:])
        if claimed is None:
            continue
        matches = _resolve_listed(sheet, a1, by_full, by_a1)
        if not matches:
            continue
        for prefix, formula in matches:
            if _same_formula(claimed, formula.formula):
                continue
            key = f"{prefix}{formula.cell}"
            if key in seen:
                continue
            seen.add(key)
            found.append((prefix, formula, claimed))
    return found


def _listed_indexes(
    pack: PackInventory,
) -> tuple[
    dict[str, list[tuple[str, FormulaInfo]]],
    dict[str, list[tuple[str, FormulaInfo]]],
]:
    by_full: dict[str, list[tuple[str, FormulaInfo]]] = {}
    by_a1: dict[str, list[tuple[str, FormulaInfo]]] = {}
    multi = len(pack.files) > 1
    for item in pack.files:
        prefix = f"{item.filename} " if multi else ""
        for formula in item.formulas:
            pair = (prefix, formula)
            by_full.setdefault(cell_address_key(formula.cell), []).append(pair)
            by_a1.setdefault(_a1_key(formula.cell), []).append(pair)
    return by_full, by_a1


def _resolve_listed(
    sheet: str | None,
    a1: str,
    by_full: dict[str, list[tuple[str, FormulaInfo]]],
    by_a1: dict[str, list[tuple[str, FormulaInfo]]],
) -> list[tuple[str, FormulaInfo]]:
    if sheet:
        return by_full.get(cell_address_key(f"{sheet}!{a1}"), [])
    matches = by_a1.get(a1.casefold(), [])
    if len(matches) != 1:
        return []
    return matches


def _cell_mentions(text: str) -> list[tuple[int, int, str | None, str]]:
    mentions: list[tuple[int, int, str | None, str]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, cell in iter_sheet_cells(text):
        sheet, a1 = cell.rsplit("!", 1)
        mentions.append((start, end, sheet, a1))
        occupied.append((start, end))
    for match in _BARE_A1.finditer(text):
        start, end = match.span()
        if any(
            start < other_end and end > other_start
            for other_start, other_end in occupied
        ):
            continue
        a1 = f"{match.group(1).upper()}{int(match.group(2))}"
        mentions.append((start, end, None, a1))
    mentions.sort(key=lambda item: item[0])
    return mentions


def _read_formula(remainder: str) -> str | None:
    text = remainder.lstrip()
    stripped = _SEP.sub("", text, count=1)
    if stripped.startswith("`"):
        close = stripped.find("`", 1)
        if close != -1:
            inner = stripped[1:close].strip()
            if _looks_like_formula(inner):
                return _display_formula(inner)
    match = _FORMULA_BODY.match(stripped)
    if match:
        return _display_formula(match.group(0))
    expr = _BARE_EXPR.match(stripped)
    if expr:
        return _display_formula("=" + expr.group(0))
    return None


def _looks_like_formula(text: str) -> bool:
    compact = "".join(text.split())
    if compact.startswith("="):
        return len(compact) > 1
    return _BARE_EXPR.match(compact) is not None


def _display_formula(text: str) -> str:
    cleaned = " ".join(text.strip().strip("`").split()).rstrip(".,;")
    if not cleaned.startswith("="):
        cleaned = "=" + cleaned
    return cleaned


def _same_formula(claimed: str, stored: str) -> bool:
    return _formula_key(claimed) == _formula_key(stored)


def _formula_key(text: str) -> str:
    compact = "".join(_display_formula(text).split()).replace("$", "")
    return compact.casefold()


def _a1_key(cell: str) -> str:
    addr = cell.rsplit("!", 1)[-1].replace("$", "")
    return addr.casefold()
