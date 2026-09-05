"""In-memory chat thread helpers. No Streamlit import — safe for pytest."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

Role = Literal["user", "assistant"]

THREAD_KEY = "chat_messages"
AWAITING_KEY = "chat_awaiting"
CONVERSATION_ID_KEY = "active_conversation_id"
AWAITING_TITLE_KEY = "chat_awaiting_title"
TITLE_CONVERSATION_ID_KEY = "title_conversation_id"
AUTO_TITLE_DONE_KEY = "auto_title_done_ids"
DELETE_DIALOG_OPEN_KEY = "delete_dialog_open"
DELETE_CONFIRMED_ID_KEY = "delete_confirmed_id"
RECENT_TITLE_MAX_CHARS = 20


def empty_thread() -> list[dict[str, Any]]:
    """Return a new conversation with no turns."""
    return []


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_when(created_at: datetime | str) -> datetime | None:
    if isinstance(created_at, str):
        if not created_at.strip():
            return None
        when = datetime.fromisoformat(created_at)
    else:
        when = created_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def format_message_stamp(created_at: datetime | str) -> str:
    """Short local date and time under a user bubble, e.g. 5 Sep 2026, 12:53."""
    when = _parse_when(created_at)
    if when is None:
        return ""
    local = when.astimezone()
    return f"{local.day} {local.strftime('%b %Y, %H:%M')}"


def format_recent_stamp(updated_at: datetime | str) -> str:
    """Short Recents date, e.g. 5 Sep. Avoids %-d (crashes on Windows)."""
    when = _parse_when(updated_at)
    if when is None:
        return ""
    local = when.astimezone()
    return f"{local.day} {local.strftime('%b')}"


def format_recent_title(
    title: str, *, max_chars: int = RECENT_TITLE_MAX_CHARS
) -> str:
    """One-line Recents title. No wraps; first 20 characters only."""
    collapsed = " ".join(title.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars]


def format_recent_button_label(title: str, updated_at: datetime | str) -> str:
    """Sidebar Recents button: truncated title plus short date."""
    short_title = format_recent_title(title)
    stamp = format_recent_stamp(updated_at)
    if stamp:
        return f"{short_title} · {stamp}"
    return short_title


def format_elapsed_label(seconds: float | int | None) -> str:
    """Human elapsed time, e.g. 42 s or 1 min 35 s."""
    if seconds is None:
        return ""
    total = max(0, int(round(float(seconds))))
    minutes, rest = divmod(total, 60)
    if minutes == 0:
        return f"{rest} s"
    return f"{minutes} min {rest:02d} s"


def format_generated_in(seconds: float | int | None) -> str:
    """Assistant stamp, e.g. Generated in 12s or Generated in 1 min 35s."""
    if seconds is None:
        return ""
    total = max(0, int(round(float(seconds))))
    minutes, rest = divmod(total, 60)
    if minutes == 0:
        return f"Generated in {rest}s"
    return f"Generated in {minutes} min {rest:02d}s"


def add_message(
    thread: list[dict[str, Any]],
    role: Role,
    content: str,
    *,
    created_at: datetime | None = None,
    elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    """Append one turn and return the stored dict."""
    when = created_at if created_at is not None else utc_now()
    message: dict[str, Any] = {
        "role": role,
        "content": content,
        "created_at": when.isoformat(),
    }
    if elapsed_seconds is not None:
        message["elapsed_seconds"] = float(elapsed_seconds)
    thread.append(message)
    return message
