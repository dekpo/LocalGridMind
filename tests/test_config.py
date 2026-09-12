"""Smoke tests for GGUF discovery. No large model files are required."""

import sys
from pathlib import Path

from src.config import (
    ModelInfo,
    get_project_root,
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
    label_for_model_path,
    list_available_models,
    resolve_reasoning_tokens,
    resolve_selected_model_label,
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


def test_get_project_root_uses_exe_folder_when_frozen(
    monkeypatch, tmp_path: Path
) -> None:
    exe = tmp_path / "LocalGridMind.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert get_project_root() == tmp_path


def _fake_models(tmp_path: Path) -> list[ModelInfo]:
    alpha = tmp_path / "alpha.gguf"
    beta = tmp_path / "Gemma-2-9b.gguf"
    alpha.write_bytes(b"x")
    beta.write_bytes(b"y")
    return [
        ModelInfo(name="alpha", path=alpha.resolve(), size_bytes=1),
        ModelInfo(name="Gemma-2-9b", path=beta.resolve(), size_bytes=2),
    ]


def test_selectbox_follows_loaded_stem_when_session_is_empty(tmp_path: Path) -> None:
    models = _fake_models(tmp_path)
    labels = [item.display_label for item in models]
    loaded = models[1].path
    chosen = resolve_selected_model_label(
        labels,
        stored=None,
        loaded_path=loaded,
        loaded_ready=True,
        models=models,
    )
    assert chosen == models[1].display_label
    assert label_for_model_path(loaded, models) == models[1].display_label


def test_selectbox_keeps_persisted_pick_when_another_model_is_loaded(
    tmp_path: Path,
) -> None:
    models = _fake_models(tmp_path)
    labels = [item.display_label for item in models]
    chosen = resolve_selected_model_label(
        labels,
        stored=models[0].display_label,
        loaded_path=models[1].path,
        loaded_ready=True,
        models=models,
    )
    assert chosen == models[0].display_label


def test_selectbox_stale_label_resyncs_to_loaded(tmp_path: Path) -> None:
    models = _fake_models(tmp_path)
    labels = [item.display_label for item in models]
    chosen = resolve_selected_model_label(
        labels,
        stored="missing (9.9 GB)",
        loaded_path=models[1].path,
        loaded_ready=True,
        models=models,
    )
    assert chosen == models[1].display_label
