"""Persist a finished generate without Streamlit session flags."""

from __future__ import annotations

from typing import Any

try:
    from ui.chat_store import add_message
    from ui.library import ConversationLibrary
except ImportError:  # pytest uses the repo root on sys.path
    from src.ui.chat_store import add_message
    from src.ui.library import ConversationLibrary


def ingest_finished_reply(
    thread: list[dict],
    library: ConversationLibrary,
    conversation_id: int,
    runtime: Any,
) -> dict | None:
    """Write last_reply / reply_error even if AWAITING was lost on reconnect."""
    if getattr(runtime, "is_generating", False):
        return None
    consume = getattr(runtime, "consume_finished_reply", None)
    if consume is None:
        return None
    content, elapsed = consume()
    if not content:
        return None
    if _already_has_assistant(thread, content):
        return None
    stored = add_message(
        thread, "assistant", content, elapsed_seconds=elapsed
    )
    library.append_message(
        conversation_id,
        "assistant",
        stored["content"],
        created_at=stored["created_at"],
        elapsed_seconds=elapsed,
    )
    return stored


def _already_has_assistant(thread: list[dict], content: str) -> bool:
    if not thread:
        return False
    last = thread[-1]
    return last.get("role") == "assistant" and last.get("content") == content
