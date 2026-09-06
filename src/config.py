"""Application paths, CPU inference limits, and dynamic GGUF discovery."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# Hard cap for Intel Core i7-150U. Do not raise this without an explicit
# product decision: extra threads freeze the Windows desktop.
N_THREADS = 4
N_GPU_LAYERS = 0
N_CTX = 4096
N_BATCH = 128
# Sidebar labels. Hidden token budgets stay under N_CTX (prompt + reply).
# Do not show these numbers or the word "token" in the UI.
REASONING_TIME_LABELS: tuple[str, ...] = (
    "~2 min",
    "~4 min",
    "~6 min",
    "~8 min",
    "~10 min",
)
REASONING_TIME_TOKENS: dict[str, int] = {
    "~2 min": 512,
    "~4 min": 1024,
    "~6 min": 1536,
    "~8 min": 2048,
    "~10 min": 2560,
}
DEFAULT_REASONING_TIME_LABEL = "~6 min"
# Chat completion budget. 512 left reasoning models with no visible
# answer on this CPU (~2 min). 1536 leaves room for a reply (~6 min).
CHAT_MAX_TOKENS = REASONING_TIME_TOKENS[DEFAULT_REASONING_TIME_LABEL]

GGUF_EXTENSION = ".gguf"


def get_project_root() -> Path:
    """Return the portable app root (source tree or frozen executable folder)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = get_project_root()
SRC_DIR = PROJECT_ROOT / "src"
MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data" / "uploads"
UPLOADS_DIR = DATA_DIR
CHATS_DIR = PROJECT_ROOT / "data" / "chats"
CHATS_DB_PATH = CHATS_DIR / "library.sqlite"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


@dataclass(frozen=True)
class ModelInfo:
    """A discovered local GGUF model."""

    name: str
    path: Path
    size_bytes: int

    @property
    def size_gb(self) -> float:
        return self.size_bytes / float(1024**3)

    @property
    def display_label(self) -> str:
        return f"{self.name} ({self.size_gb:.1f} GB)"


def ensure_runtime_directories() -> None:
    """Create folders that must exist at runtime but stay empty in Git."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def list_available_models(models_dir: Path | None = None) -> list[ModelInfo]:
    """Scan models/ (non-recursive) and return sorted GGUF files.

    The UI must use this list for the model dropdown so the app stays
    model-agnostic: drop a new .gguf file, restart or refresh, select it.
    """
    directory = models_dir if models_dir is not None else MODELS_DIR
    if not directory.is_dir():
        return []

    discovered: list[ModelInfo] = []
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() != GGUF_EXTENSION:
            continue
        discovered.append(
            ModelInfo(
                name=entry.stem,
                path=entry.resolve(),
                size_bytes=entry.stat().st_size,
            )
        )

    discovered.sort(key=lambda item: item.name.lower())
    return discovered


def get_model_labels() -> list[str]:
    """Return dropdown labels for Streamlit selectbox widgets."""
    return [model.display_label for model in list_available_models()]


def resolve_model_by_label(label: str) -> ModelInfo | None:
    """Map a dropdown label back to the discovered model."""
    for model in list_available_models():
        if model.display_label == label:
            return model
    return None


def resolve_reasoning_tokens(label: str) -> int:
    """Map a Reasoning time label to the hidden chat completion budget."""
    return REASONING_TIME_TOKENS.get(label, CHAT_MAX_TOKENS)
