"""Workbook packs, schema inventory, and formula / link extraction."""

from .inventory import build_pack_inventory
from .packs import attach_uploads_to_conversation
from .prompt import build_chat_prompt

__all__ = [
    "attach_uploads_to_conversation",
    "build_chat_prompt",
    "build_pack_inventory",
]
