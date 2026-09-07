"""Prompt adapter: inject a compact inventory. Never send workbook bytes."""

from __future__ import annotations

try:
    from llm.runtime import RETRY_STEER_PREFIX
except ImportError:  # pytest uses the repo root on sys.path
    from src.llm.runtime import RETRY_STEER_PREFIX

INVENTORY_PREAMBLE = (
    "You are helping a finance analyst understand spreadsheet structure and logic. "
    "The workbook inventory is the only source of truth. "
    "Use only the workbook inventory below. "
    "If a formula, named range, link, or cell is not listed, say it is not "
    "in the inventory. "
    "Do not invent cell addresses or named ranges. "
    "Never invent workbook names, file names, sheet names, existing formulas, "
    "existing values, or links. "
    "Do not invent numeric answers. "
    "When referring to an existing workbook formula, NEVER reproduce the "
    "formula text yourself. Use [[FORMULA:Sheet Name!A1]] instead. "
    "In a multi-file pack you may write [[FORMULA:File.xlsx!A1]] when that "
    "A1 address is unique in that file. "
    "Only use that reference if the exact cell is present in the supplied "
    "inventory. The application will resolve the formula from the local "
    "workbook inventory. "
    "If you want to suggest a formula that does not come from the workbook, "
    "label it on its own line as SUGGESTED FORMULA: then the formula. "
    "Never present a suggested formula as an existing workbook formula. "
    "If you are unsure whether something exists in the workbook, say that "
    "it could not be verified. "
    "You may explain listed formulas, named ranges, and links. "
    "Do not write Python."
)

NO_PACK_PREAMBLE = (
    "You are helping a finance analyst with spreadsheets. "
    "No workbook is attached to this chat yet. "
    "Do not invent numeric answers or pretend to have opened a file."
)


def build_chat_prompt(
    user_text: str,
    inventory_text: str | None = None,
    *,
    retry: bool = False,
) -> str:
    """Wrap the analyst question. Inventory is optional and already compact."""
    question = user_text.strip()
    if retry:
        question = f"{RETRY_STEER_PREFIX}{question}"
    if inventory_text and inventory_text.strip():
        return (
            f"{INVENTORY_PREAMBLE}\n\n"
            f"Workbook inventory:\n{inventory_text.strip()}\n\n"
            f"Analyst question:\n{question}"
        )
    return f"{NO_PACK_PREAMBLE}\n\nAnalyst question:\n{question}"
