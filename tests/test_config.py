"""Smoke tests for GGUF discovery. No large model files are required."""

from pathlib import Path

from src.config import (
    CHAT_MAX_TOKENS,
    CHATS_DB_PATH,
    CHATS_DIR,
    DATA_DIR,
    DEFAULT_REASONING_TIME_LABEL,
    N_CTX,
    PROJECT_ROOT,
    REASONING_TIME_LABELS,
    REASONING_TIME_TOKENS,
    UPLOADS_DIR,
    list_available_models,
    resolve_reasoning_tokens,
)


def test_list_available_models_ignores_non_gguf(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    (tmp_path / "alpha.gguf").write_bytes(b"fake")
    (tmp_path / "Beta.GGUF").write_bytes(b"fake")

    models = list_available_models(tmp_path)

    names = [item.name for item in models]
    assert names == ["alpha", "Beta"]
    assert all(item.path.suffix.lower() == ".gguf" for item in models)


def test_list_available_models_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert list_available_models(missing) == []


def test_chats_db_path_is_under_data_chats() -> None:
    assert CHATS_DIR == PROJECT_ROOT / "data" / "chats"
    assert CHATS_DB_PATH == CHATS_DIR / "library.sqlite"
    assert DATA_DIR == PROJECT_ROOT / "data" / "uploads"
    assert UPLOADS_DIR == DATA_DIR


def test_chat_token_budget_leaves_room_for_a_visible_reply() -> None:
    assert CHAT_MAX_TOKENS == 1536


def test_reasoning_time_labels_map_to_hidden_token_budgets() -> None:
    assert DEFAULT_REASONING_TIME_LABEL == "~6 min"
    assert REASONING_TIME_LABELS == (
        "~2 min",
        "~4 min",
        "~6 min",
        "~8 min",
        "~10 min",
    )
    assert resolve_reasoning_tokens("~2 min") == 512
    assert resolve_reasoning_tokens("~4 min") == 1024
    assert resolve_reasoning_tokens("~6 min") == 1536
    assert resolve_reasoning_tokens("~8 min") == 2048
    assert resolve_reasoning_tokens("~10 min") == 2560
    assert resolve_reasoning_tokens(DEFAULT_REASONING_TIME_LABEL) == CHAT_MAX_TOKENS
    assert max(REASONING_TIME_TOKENS.values()) < N_CTX


def test_unknown_reasoning_time_label_uses_default_budget() -> None:
    assert resolve_reasoning_tokens("not a label") == CHAT_MAX_TOKENS
