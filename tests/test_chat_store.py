"""Chat thread helpers. No GGUF and no Streamlit runtime required."""

from __future__ import annotations

from datetime import datetime, timezone

from src.ui.chat_store import (
    RECENT_TITLE_MAX_CHARS,
    WAIT_COPY_AFTER_300,
    WAIT_COPY_UNDER_90,
    WAIT_COPY_UNDER_180,
    WAIT_COPY_UNDER_300,
    add_message,
    empty_thread,
    format_elapsed_label,
    format_generated_in,
    format_message_stamp,
    format_recent_button_label,
    format_recent_stamp,
    format_recent_title,
    generating_wait_copy,
    last_user_content,
)


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


def test_format_recent_stamp_is_short_and_windows_safe() -> None:
    stamp = format_recent_stamp("2026-09-05T10:53:00+00:00")
    assert "Sep" in stamp
    assert "5" in stamp
    assert ":" not in stamp


def test_format_recent_title_is_one_line_and_max_20() -> None:
    long_title = "Je veux savoir qui tu es et ce que tu peux"
    short = format_recent_title(long_title)
    assert short == long_title[:RECENT_TITLE_MAX_CHARS]
    assert len(short) == 20
    assert "\n" not in short
    assert format_recent_title("New chat") == "New chat"
    assert format_recent_title("line one\nline two") == "line one line two"


def test_format_recent_button_label_keeps_date() -> None:
    label = format_recent_button_label(
        "Je veux savoir qui tu es et ce que tu peux",
        "2026-09-05T10:53:00+00:00",
    )
    assert label.startswith("Je veux savoir qui t")
    assert " · " in label
    assert "Sep" in label


def test_format_elapsed_label() -> None:
    assert format_elapsed_label(None) == ""
    assert format_elapsed_label(0) == "0 s"
    assert format_elapsed_label(42) == "42 s"
    assert format_elapsed_label(95) == "1 min 35 s"


def test_format_generated_in() -> None:
    assert format_generated_in(None) == ""
    assert format_generated_in(12) == "Generated in 12s"
    assert format_generated_in(95) == "Generated in 1 min 35s"


def test_add_message_can_store_elapsed_seconds() -> None:
    thread = empty_thread()
    stored = add_message(thread, "assistant", "Ready.", elapsed_seconds=95)
    assert stored["elapsed_seconds"] == 95.0


def test_assistant_turn_appends_after_user() -> None:
    thread = empty_thread()
    add_message(thread, "user", "Hello")
    add_message(thread, "assistant", "Ready to help.")
    assert [item["role"] for item in thread] == ["user", "assistant"]


def test_generating_wait_copy_changes_with_elapsed_time() -> None:
    assert generating_wait_copy(0) == WAIT_COPY_UNDER_90
    assert generating_wait_copy(89) == WAIT_COPY_UNDER_90
    assert generating_wait_copy(90) == WAIT_COPY_UNDER_180
    assert generating_wait_copy(179) == WAIT_COPY_UNDER_180
    assert generating_wait_copy(180) == WAIT_COPY_UNDER_300
    assert generating_wait_copy(299) == WAIT_COPY_UNDER_300
    assert generating_wait_copy(300) == WAIT_COPY_AFTER_300
    assert "not sleeping" in WAIT_COPY_AFTER_300


def test_last_user_content_returns_latest_user_turn() -> None:
    thread = empty_thread()
    assert last_user_content(thread) is None
    add_message(thread, "user", "first")
    add_message(thread, "assistant", "ok")
    add_message(thread, "user", "second")
    assert last_user_content(thread) == "second"
