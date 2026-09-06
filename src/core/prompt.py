"""Prompt adapter: inject a compact inventory. Never send workbook bytes."""

from __future__ import annotations

try:
    from llm.runtime import RETRY_STEER_PREFIX
except ImportError:  # pytest uses the repo root on sys.path
    from src.llm.runtime import RETRY_STEER_PREFIX

INVENTORY_PREAMBLE = (
    "You are helping a finance analyst understand spreadsheet structure and logic. "
    "Use only the workbook inventory below. "
    "If a formula, named range, link, or cell is not listed, say it is not "
    "in the inventory. "
    "Do not invent cell addresses or named ranges. "
    "Do not invent numeric answers. "
    "You may explain listed formulas, named ranges, and links, and you may "
    "suggest Excel formula text the analyst can paste. "
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
