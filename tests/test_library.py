"""Conversation library tests. Uses tmp_path — never the real chats DB."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.config import CHATS_DB_PATH
from src.ui.library import (
    DEFAULT_TITLE,
    ConversationLibrary,
    build_title_prompt,
    heuristic_title,
    sanitize_model_title,
)


def _library(tmp_path: Path) -> ConversationLibrary:
    return ConversationLibrary(tmp_path / "library.sqlite")


def test_create_and_list_conversations(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.create_conversation()
    second = library.create_conversation("Rates pack")

    listed = library.list_conversations()
    assert [item.id for item in listed] == [second.id, first.id]
    assert first.title == DEFAULT_TITLE
    assert second.title == "Rates pack"
    assert library.get_conversation(first.id) is not None


def test_append_and_load_messages(tmp_path: Path) -> None:
    library = _library(tmp_path)
    conversation = library.create_conversation()
    library.append_message(conversation.id, "user", "Explain the join")
    library.append_message(conversation.id, "assistant", "The join uses the key.")

    messages = library.list_messages(conversation.id)
    assert [item.role for item in messages] == ["user", "assistant"]
    assert messages[0].content == "Explain the join"
    assert messages[0].as_thread_item()["created_at"]
    assert library.first_user_content(conversation.id) == "Explain the join"


def test_append_updates_recents_order(tmp_path: Path) -> None:
    library = _library(tmp_path)
    older = library.create_conversation("Older")
    newer = library.create_conversation("Newer")
    library.append_message(older.id, "user", "Bump")

    listed = library.list_conversations()
    assert [item.id for item in listed] == [older.id, newer.id]


def test_set_title_and_needs_auto_title(tmp_path: Path) -> None:
    library = _library(tmp_path)
    conversation = library.create_conversation()
    assert library.needs_auto_title(conversation.id) is False

    library.append_message(conversation.id, "user", "Map the lookup keys")
    library.append_message(conversation.id, "assistant", "Use the id column.")
    assert library.needs_auto_title(conversation.id) is True

    library.set_title(conversation.id, "Lookup keys")
    updated = library.get_conversation(conversation.id)
    assert updated is not None
    assert updated.title == "Lookup keys"
    assert library.needs_auto_title(conversation.id) is False


def test_heuristic_title_truncates_without_inventing_numbers() -> None:
    assert heuristic_title("") == DEFAULT_TITLE
    assert heuristic_title("  Explain VLOOKUP  ") == "Explain VLOOKUP"
    long_text = (
        "Please walk through the nested lookup on the rates sheet "
        "and then explain every linked workbook used by the close pack"
    )
    titled = heuristic_title(long_text)
    assert len(titled) <= 48
    assert titled.startswith("Please walk through")
    assert titled != long_text
    # Does not invent figures that were not in the user line.
    assert "2026" not in titled


def test_sanitize_model_title_strips_think_and_quotes() -> None:
    raw = '<think>plan</think> "Rates lookup"'
    assert sanitize_model_title(raw) == "Rates lookup"
    assert sanitize_model_title("<think>only hidden</think>") == ""


def test_title_prompt_asks_for_short_title_without_numbers() -> None:
    prompt = build_title_prompt("Explain the join on book id")
    assert "6 words" in prompt
    assert "Do not invent numbers" in prompt
    assert "Explain the join on book id" in prompt


def test_append_message_stores_elapsed_seconds(tmp_path: Path) -> None:
    library = _library(tmp_path)
    conversation = library.create_conversation()
    library.append_message(
        conversation.id,
        "assistant",
        "Ready.",
        elapsed_seconds=95.0,
    )
    stored = library.list_messages(conversation.id)[0]
    assert stored.elapsed_seconds == 95.0
    assert stored.as_thread_item()["elapsed_seconds"] == 95.0


def test_delete_conversation_removes_messages(tmp_path: Path) -> None:
    library = _library(tmp_path)
    doomed = library.create_conversation("Doomed")
    keep = library.create_conversation("Keep")
    library.append_message(doomed.id, "user", "Bye")
    library.delete_conversation(doomed.id)

    assert library.get_conversation(doomed.id) is None
    assert library.list_messages(doomed.id) == []
    assert library.get_conversation(keep.id) is not None
    with pytest.raises(KeyError):
        library.delete_conversation(doomed.id)


def test_migrates_elapsed_seconds_on_existing_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO conversations (title, created_at, updated_at)
            VALUES ('Legacy', '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00');
            """
        )
        conn.commit()
    finally:
        conn.close()

    library = ConversationLibrary(db_path)
    library.append_message(1, "assistant", "Hi", elapsed_seconds=12)
    assert library.list_messages(1)[0].elapsed_seconds == 12.0


def test_unknown_conversation_raises(tmp_path: Path) -> None:
    library = _library(tmp_path)
    with pytest.raises(KeyError):
        library.append_message(99, "user", "missing")
    with pytest.raises(KeyError):
        library.set_title(99, "Gone")


def test_library_never_uses_the_real_app_db(tmp_path: Path) -> None:
    library = _library(tmp_path)
    library.create_conversation()
    assert library.db_path != CHATS_DB_PATH
    assert library.db_path.parent == tmp_path


def test_connections_close_and_wal_is_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    library = ConversationLibrary(db_path)
    conversation = library.create_conversation()
    library.append_message(conversation.id, "user", "Hello")

    conn = sqlite3.connect(str(db_path))
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
        count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        assert count == 1
    finally:
        conn.close()
