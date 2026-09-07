"""Resolve [[FORMULA:Sheet!A1]] tokens from the local inventory. No LLM."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .inventory import (
    FormulaInfo,
    PackInventory,
    cell_address_key,
    indexed_formulas,
    is_workbook_name,
)

logger = logging.getLogger(__name__)

FORMULA_REF_RE = re.compile(r"\[\[FORMULA:([^\]]+)\]\]")
_FOLLOW_SEP = re.compile(
    r"^\s*(?:which\s+is|that\s+is|equals|equal(?:\s+to)?|is|:)\s*",
    re.I,
)
_EQ_BODY = re.compile(
    r"=\s*[\w+\-*/()\[\],'.!_:$%^&<>]+(?:\s*[\w+\-*/()\[\],'.!_:$%^&<>]+)*",
    re.I,
)
_BARE_A1 = re.compile(r"^\$?[A-Za-z]{1,3}\$?\d+$")

UNVERIFIED_REF = "[formula reference could not be verified: {ref}]"
UNVERIFIED_NOTICE = (
    "⚠️ One or more workbook references could not be verified "
    "against the local inventory."
)
COMPETING_NOTE = (
    "The stored formula for `{cell}` is `{stored}`. "
    "Other formula text next to that reference was not verified."
)


def build_formula_index(
    inventory: PackInventory,
) -> dict[str, FormulaInfo]:
    """Map qualified keys to stored formulas. Exact keys only; no fuzzy match.

    Keys are `sheet!a1` when that address is unique in the pack, always
    `filename::sheet!a1`, and `filename::a1` when that A1 is unique in
    that workbook. Bare A1 without a file or sheet is never a key.
    """
    by_file: dict[str, FormulaInfo] = {}
    by_cell: dict[str, FormulaInfo] = {}
    collisions: set[str] = set()
    per_file_a1: dict[str, dict[str, list[FormulaInfo]]] = {}
    for item in inventory.files:
        filename = Path(item.filename).name.casefold()
        file_a1 = per_file_a1.setdefault(filename, {})
        for formula in indexed_formulas(item):
            if "!" not in formula.cell:
                continue
            cell_key = cell_address_key(formula.cell)
            by_file[f"{filename}::{cell_key}"] = formula
            a1 = _a1_key(formula.cell)
            file_a1.setdefault(a1, []).append(formula)
            if cell_key in collisions:
                continue
            if cell_key in by_cell:
                del by_cell[cell_key]
                collisions.add(cell_key)
                continue
            by_cell[cell_key] = formula
    for filename, groups in per_file_a1.items():
        for a1, rows in groups.items():
            if len(rows) == 1:
                by_file[f"{filename}::{a1}"] = rows[0]
    by_file.update(by_cell)
    return by_file


def resolve_formula_ref(
    reference: str, inventory: PackInventory
) -> FormulaInfo | None:
    """Return the stored formula for an exact reference, or None."""
    return _lookup_indexed(reference, build_formula_index(inventory))


def resolve_formula_refs(
    text: str, inventory: PackInventory
) -> tuple[str, list[str]]:
    """Replace [[FORMULA:…]] with the stored formula. Fail closed on misses."""
    index = build_formula_index(inventory)
    errors: list[str] = []
    competing: list[tuple[str, str]] = []
    seen_competing: set[str] = set()

    def replacer(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        formula = _lookup_indexed(raw, index)
        if formula is None:
            errors.append(raw)
            logger.warning("Formula reference could not be resolved: %s", raw)
            return UNVERIFIED_REF.format(ref=raw)
        display = formula.cell
        logger.info("Formula reference resolved: %s", display)
        claimed = _following_formula(text[match.end() :])
        if claimed and not _formulas_match(claimed, formula.formula):
            key = cell_address_key(display)
            if key not in seen_competing:
                seen_competing.add(key)
                competing.append((display, formula.formula))
        return f"{display} → {formula.formula}"

    resolved = FORMULA_REF_RE.sub(replacer, text)
    extras: list[str] = []
    if competing:
        extras.extend(
            COMPETING_NOTE.format(cell=cell, stored=stored)
            for cell, stored in competing
        )
    if errors:
        extras.append(UNVERIFIED_NOTICE)
    if extras:
        resolved = resolved.rstrip() + "\n\n" + "\n".join(extras)
    return resolved, errors


def resolve_formula_refs_from_json(
    text: str, inventory_json: str
) -> tuple[str, list[str]]:
    """Same resolver against persisted JSON. Do not re-parse workbook files."""
    return resolve_formula_refs(text, PackInventory.from_json(inventory_json))


def _lookup_indexed(
    reference: str, index: dict[str, FormulaInfo]
) -> FormulaInfo | None:
    filename, rest = _split_ref(reference)
    if not rest:
        return None
    if filename:
        book = Path(filename.replace("\\", "/")).name.casefold()
        if "!" in rest:
            return index.get(f"{book}::{cell_address_key(rest)}")
        if _BARE_A1.match(rest):
            return index.get(f"{book}::{_a1_key(rest)}")
        return None
    if "!" not in rest:
        return None
    return index.get(cell_address_key(rest))


def _split_ref(reference: str) -> tuple[str | None, str]:
    """Split `file.xlsx::Sheet!A1`, `file.xlsx!A1`, or `Sheet!A1`."""
    text = " ".join(str(reference).strip().strip("`").split())
    if "::" in text:
        book, cell = text.split("::", 1)
        return book.strip() or None, cell.strip()
    bang = text.find("!")
    if bang > 0:
        head = text[:bang].strip()
        tail = text[bang + 1 :].strip()
        if is_workbook_name(head) and tail:
            return Path(head.replace("\\", "/")).name, tail
    return None, text


def _a1_key(cell_or_a1: str) -> str:
    addr = str(cell_or_a1).rsplit("!", 1)[-1]
    return addr.replace("$", "").casefold()


def _following_formula(remainder: str) -> str | None:
    stripped = _FOLLOW_SEP.sub("", remainder.lstrip(), count=1)
    if stripped.startswith("`"):
        close = stripped.find("`", 1)
        if close != -1:
            inner = stripped[1:close].strip()
            if inner.startswith("=") and len(inner) > 1:
                return inner
    match = _EQ_BODY.match(stripped)
    if match:
        return match.group(0).strip()
    return None


def _formulas_match(left: str, right: str) -> bool:
    return _formula_key(left) == _formula_key(right)


def _formula_key(text: str) -> str:
    compact = "".join(str(text).strip().strip("`").split()).replace("$", "")
    if not compact.startswith("="):
        compact = "=" + compact
    return compact.casefold()
