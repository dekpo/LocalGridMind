"""CPU-only llama.cpp wrapper: one GGUF in memory at a time."""

from __future__ import annotations

import gc
import re
import threading
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from config import N_BATCH, N_CTX, N_GPU_LAYERS, N_THREADS
except ImportError:  # pytest uses the repo root on sys.path
    from src.config import N_BATCH, N_CTX, N_GPU_LAYERS, N_THREADS

LlamaFactory = Callable[..., Any]

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_UNCLOSED = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)

SMOKE_PROMPT = (
    "Reply with one short English sentence confirming you are ready "
    "to help analyze spreadsheets. Do not invent any numbers."
)

SMOKE_MAX_TOKENS = 512

EMPTY_REPLY_NOTICE = (
    "The model produced only hidden reasoning for this message. "
    "Try Generate again, or use a shorter test message."
)


class RuntimeStatus(str, Enum):
    """User-visible runtime states."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


class ModelNotReadyError(RuntimeError):
    """Raised when generate() is called without a loaded model."""


def strip_reasoning_tags(text: str) -> str:
    """Remove model reasoning wrappers before any user-visible text."""
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _THINK_UNCLOSED.sub("", cleaned)
    return cleaned.strip()


def explain_load_error(exc: BaseException) -> str:
    """Map engine failures to short English text the sidebar can show."""
    text = str(exc) or exc.__class__.__name__
    lowered = text.lower()
    win_code = getattr(exc, "winerror", None)
    if win_code == 4551 or "4551" in text or "contrôle d’application" in lowered:
        return (
            "Windows blocked the local model engine (application control, "
            "error 4551). Allow llama.dll for this app in Windows Security, "
            "or turn off Smart App Control, then load the model again. "
            "This is a Windows policy, not a problem with the model file."
        )
    if "failed to load shared library" in lowered or "llama.dll" in lowered:
        return (
            "Windows could not start the local model engine. "
            "Check Windows Security, then try Load model again."
        )
    return text


def _default_llama_factory(model_path: str, **kwargs: Any) -> Any:
    """Build Llama and attach llama.cpp's 0.0–1.0 load-progress callback."""
    from llama_cpp import Llama
    import llama_cpp.llama_cpp as llama_c

    progress_hook = kwargs.pop("progress_hook", None)
    if progress_hook is None:
        return Llama(model_path=model_path, **kwargs)

    original_defaults = llama_c.llama_model_default_params
    keepalive: list[Any] = []

    def _patched_defaults() -> Any:
        params = original_defaults()

        def _on_progress(fraction: float, _user_data: Any) -> bool:
            try:
                progress_hook(float(fraction))
            except Exception:
                pass
            return True

        c_callback = llama_c.llama_progress_callback(_on_progress)
        keepalive.append((_on_progress, c_callback))
        params.progress_callback = c_callback
        return params

    llama_c.llama_model_default_params = _patched_defaults
    try:
        llama = Llama(model_path=model_path, **kwargs)
    finally:
        llama_c.llama_model_default_params = original_defaults
    llama._lgm_progress_keepalive = keepalive
    return llama


class ModelRuntime:
    """Load, unload, and generate with a single local GGUF.

    The Llama instance is created only when load() / start_load() runs.
    Importing this module does not open a model file.
    """

    def __init__(self, llama_factory: LlamaFactory | None = None) -> None:
        self._llama_factory = llama_factory or _default_llama_factory
        self._lock = threading.RLock()
        self._llama: Any | None = None
        self._status = RuntimeStatus.UNLOADED
        self._error: str | None = None
        self._loaded_path: Path | None = None
        self._generation = 0
        self._load_progress: float | None = None
        self._load_started_at: float | None = None
        self._generating = False
        self._generate_started_at: float | None = None
        self._last_reply: str | None = None
        self._reply_error: str | None = None

    @property
    def status(self) -> RuntimeStatus:
        with self._lock:
            return self._status

    @property
    def error_message(self) -> str | None:
        with self._lock:
            return self._error

    @property
    def loaded_path(self) -> Path | None:
        with self._lock:
            return self._loaded_path

    def is_ready(self) -> bool:
        return self.status is RuntimeStatus.READY

    @property
    def load_progress(self) -> float | None:
        """Tensor-load fraction from llama.cpp, or None before the first tick."""
        with self._lock:
            return self._load_progress

    @property
    def load_elapsed_seconds(self) -> float:
        with self._lock:
            started = self._load_started_at
        if started is None:
            return 0.0
        return max(0.0, time.monotonic() - started)

    @property
    def is_generating(self) -> bool:
        with self._lock:
            return self._generating

    @property
    def last_reply(self) -> str | None:
        with self._lock:
            return self._last_reply

    @property
    def reply_error(self) -> str | None:
        with self._lock:
            return self._reply_error

    @property
    def generate_elapsed_seconds(self) -> float:
        with self._lock:
            started = self._generate_started_at
        if started is None:
            return 0.0
        return max(0.0, time.monotonic() - started)

    def load(self, model_path: Path) -> None:
        """Load a GGUF on this thread. Unloads any previous model first."""
        path = Path(model_path)
        with self._lock:
            if self._status is RuntimeStatus.READY and self._loaded_path == path:
                return
            self._generation += 1
            generation = self._generation
            self._release_locked()
            self._begin_loading_locked(path)
        self._build_llama(path, generation)

    def start_load(self, model_path: Path) -> None:
        """Begin a background load so the Streamlit script can return."""
        path = Path(model_path)
        with self._lock:
            if self._status is RuntimeStatus.LOADING and self._loaded_path == path:
                return
            if self._status is RuntimeStatus.READY and self._loaded_path == path:
                return
            self._generation += 1
            generation = self._generation
            self._release_locked()
            self._begin_loading_locked(path)
        worker = threading.Thread(
            target=self._build_llama,
            args=(path, generation),
            name="localgridmind-gguf-load",
            daemon=True,
        )
        worker.start()

    def unload(self) -> None:
        """Drop the in-memory model so another GGUF can be loaded later."""
        with self._lock:
            self._generation += 1
            self._release_locked()

    def generate(self, prompt: str, *, max_tokens: int = SMOKE_MAX_TOKENS) -> str:
        """Run one completion and return text safe to show to an analyst."""
        with self._lock:
            if self._status is not RuntimeStatus.READY or self._llama is None:
                raise ModelNotReadyError(
                    "Load a local model before generating a reply."
                )
            llama = self._llama
        raw = self._complete(llama, prompt, max_tokens=max_tokens)
        cleaned = strip_reasoning_tags(raw)
        return cleaned if cleaned else EMPTY_REPLY_NOTICE

    def start_generate(self, prompt: str, *, max_tokens: int = SMOKE_MAX_TOKENS) -> None:
        """Begin a background completion so the Streamlit script can return."""
        with self._lock:
            if self._generating:
                return
            if self._status is not RuntimeStatus.READY or self._llama is None:
                self._reply_error = "Load a local model before generating a reply."
                self._last_reply = None
                return
            self._generating = True
            self._generate_started_at = time.monotonic()
            self._last_reply = None
            self._reply_error = None
        worker = threading.Thread(
            target=self._generate_worker,
            args=(prompt, max_tokens),
            name="localgridmind-gguf-generate",
            daemon=True,
        )
        worker.start()

    def _generate_worker(self, prompt: str, max_tokens: int) -> None:
        try:
            reply = self.generate(prompt, max_tokens=max_tokens)
        except Exception as exc:
            with self._lock:
                self._generating = False
                self._generate_started_at = None
                self._last_reply = None
                self._reply_error = str(exc) or exc.__class__.__name__
            return
        with self._lock:
            self._generating = False
            self._generate_started_at = None
            self._last_reply = reply
            self._reply_error = None

    def _build_llama(self, path: Path, generation: int) -> None:
        def on_progress(fraction: float) -> None:
            with self._lock:
                if generation != self._generation:
                    return
                self._load_progress = max(0.0, min(1.0, fraction))

        try:
            llama = self._llama_factory(
                str(path),
                n_threads=N_THREADS,
                n_gpu_layers=N_GPU_LAYERS,
                n_ctx=N_CTX,
                n_batch=N_BATCH,
                verbose=False,
                progress_hook=on_progress,
            )
        except TypeError:
            # Test doubles may not accept progress_hook.
            try:
                llama = self._llama_factory(
                    str(path),
                    n_threads=N_THREADS,
                    n_gpu_layers=N_GPU_LAYERS,
                    n_ctx=N_CTX,
                    n_batch=N_BATCH,
                    verbose=False,
                )
            except Exception as exc:
                self._mark_error(path, generation, exc)
                return
        except Exception as exc:  # llama.cpp can raise several types
            self._mark_error(path, generation, exc)
            return

        with self._lock:
            if generation != self._generation:
                self._close_llama(llama)
                return
            self._llama = llama
            self._status = RuntimeStatus.READY
            self._error = None
            self._loaded_path = path
            self._load_progress = 1.0
            self._load_started_at = None

    def _begin_loading_locked(self, path: Path) -> None:
        self._status = RuntimeStatus.LOADING
        self._error = None
        self._loaded_path = path
        self._load_progress = 0.0
        self._load_started_at = time.monotonic()

    def _mark_error(self, path: Path, generation: int, exc: Exception) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._llama = None
            self._status = RuntimeStatus.ERROR
            self._error = explain_load_error(exc)
            self._loaded_path = path
            self._load_progress = None
            self._load_started_at = None

    def _release_locked(self) -> None:
        llama = self._llama
        self._llama = None
        self._status = RuntimeStatus.UNLOADED
        self._error = None
        self._loaded_path = None
        self._load_progress = None
        self._load_started_at = None
        self._generating = False
        self._generate_started_at = None
        self._last_reply = None
        self._reply_error = None
        self._close_llama(llama)

    @staticmethod
    def _close_llama(llama: Any | None) -> None:
        if llama is None:
            return
        close = getattr(llama, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        del llama
        gc.collect()

    @staticmethod
    def _complete(llama: Any, prompt: str, *, max_tokens: int) -> str:
        if hasattr(llama, "create_chat_completion"):
            result = llama.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
            )
            choices = result.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                content = message.get("content")
                if content:
                    return str(content)
                text = choices[0].get("text")
                if text:
                    return str(text)
            return ""

        result = llama(
            prompt,
            max_tokens=max_tokens,
            temperature=0.2,
            echo=False,
        )
        choices = result.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("text") or "")


_RUNTIME: ModelRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def get_runtime() -> ModelRuntime:
    """Process-wide singleton. Safe across Streamlit reruns; does not load."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = ModelRuntime()
        return _RUNTIME


def reset_runtime_for_tests() -> None:
    """Drop the singleton so unit tests stay isolated."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            _RUNTIME.unload()
        _RUNTIME = None
