"""Chat thread helpers. No GGUF and no Streamlit runtime required."""

from __future__ import annotations

from datetime import datetime, timezone

from src.ui.chat_store import add_message, empty_thread, format_message_stamp


def test_empty_thread_is_a_new_list() -> None:
    first = empty_thread()
    second = empty_thread()
    assert first == []
    assert first is not second


def test_add_message_stores_role_content_and_timestamp() -> None:
    thread = empty_thread()
    when = datetime(2026, 9, 5, 10, 53, tzinfo=timezone.utc)
    stored = add_message(thread, "user", "Hello", created_at=when)

    assert len(thread) == 1
    assert stored["role"] == "user"
    assert stored["content"] == "Hello"
    assert stored["created_at"] == when.isoformat()


def test_format_message_stamp_from_isoformat() -> None:
    stamp = format_message_stamp("2026-09-05T10:53:00+00:00")
    assert "2026" in stamp
    assert ":" in stamp


def test_assistant_turn_appends_after_user() -> None:
    thread = empty_thread()
    add_message(thread, "user", "Hello")
    add_message(thread, "assistant", "Ready to help.")
    assert [item["role"] for item in thread] == ["user", "assistant"]
