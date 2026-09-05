"""Smoke tests for GGUF discovery. No large model files are required."""

from pathlib import Path

from src.config import CHATS_DB_PATH, CHATS_DIR, PROJECT_ROOT, list_available_models


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
