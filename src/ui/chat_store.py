"""In-memory chat thread helpers. No Streamlit import — safe for pytest."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

Role = Literal["user", "assistant"]

THREAD_KEY = "chat_messages"
AWAITING_KEY = "chat_awaiting"


def empty_thread() -> list[dict[str, Any]]:
    """Return a new conversation with no turns."""
    return []


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_message_stamp(created_at: datetime | str) -> str:
    """Short local date and time under a user bubble, e.g. 5 Sep 2026, 12:53."""
    if isinstance(created_at, str):
        if not created_at.strip():
            return ""
        when = datetime.fromisoformat(created_at)
    else:
        when = created_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone()
    return f"{local.day} {local.strftime('%b %Y, %H:%M')}"


def add_message(
    thread: list[dict[str, Any]],
    role: Role,
    content: str,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Append one turn and return the stored dict."""
    when = created_at if created_at is not None else utc_now()
    message = {
        "role": role,
        "content": content,
        "created_at": when.isoformat(),
    }
    thread.append(message)
    return message
