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
    from config import CHAT_MAX_TOKENS, N_BATCH, N_CTX, N_GPU_LAYERS, N_THREADS
except ImportError:  # pytest uses the repo root on sys.path
    from src.config import CHAT_MAX_TOKENS, N_BATCH, N_CTX, N_GPU_LAYERS, N_THREADS

LlamaFactory = Callable[..., Any]

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_UNCLOSED = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)

SMOKE_PROMPT = (
    "Reply with one short English sentence confirming you are ready "
    "to help analyze spreadsheets. Do not invent any numbers."
)

TITLE_MAX_TOKENS = 48

EMPTY_REPLY_NOTICE = (
    "The model used all its time preparing and did not write an answer. "
    "Try a shorter question, or generate again."
)
STOPPED_NOTICE = "Generation stopped."
RETRY_STEER_PREFIX = (
    "Answer now in plain English. Keep hidden reasoning very short. "
    "Do not spend the whole reply thinking.\n\n"
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


def build_retry_prompt(user_text: str) -> str:
    """Steer a second attempt toward a visible answer, not more thinking."""
    return f"{RETRY_STEER_PREFIX}{user_text.strip()}"


def is_retryable_notice(content: str) -> bool:
    """True when the last assistant turn may offer Generate again."""
    return content in (EMPTY_REPLY_NOTICE, STOPPED_NOTICE)


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
        self._last_generate_seconds: float | None = None
        self._last_reply: str | None = None
        self._reply_error: str | None = None
        self._titling = False
        self._last_title: str | None = None
        self._title_error: str | None = None
        self._cancel_generate = False

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
    def is_titling(self) -> bool:
        with self._lock:
            return self._titling

    @property
    def last_reply(self) -> str | None:
        with self._lock:
            return self._last_reply

    @property
    def reply_error(self) -> str | None:
        with self._lock:
            return self._reply_error

    @property
    def last_title(self) -> str | None:
        with self._lock:
            return self._last_title

    @property
    def title_error(self) -> str | None:
        with self._lock:
            return self._title_error

    @property
    def generate_elapsed_seconds(self) -> float:
        with self._lock:
            started = self._generate_started_at
        if started is None:
            return 0.0
        return max(0.0, time.monotonic() - started)

    @property
    def last_generate_seconds(self) -> float | None:
        """Elapsed seconds of the last finished generate, or None."""
        with self._lock:
            return self._last_generate_seconds

    @property
    def is_cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_generate

    def consume_finished_reply(self) -> tuple[str | None, float | None]:
        """Take a finished generate so a reconnect can still persist it.

        Clears last_reply / reply_error. Leaves last_generate_seconds.
        Returns (None, None) while generating or when nothing is waiting.
        """
        with self._lock:
            if self._generating:
                return None, None
            error = self._reply_error
            reply = self._last_reply
            elapsed = self._last_generate_seconds
            if not error and not reply:
                return None, None
            self._reply_error = None
            self._last_reply = None
            return (error or reply), elapsed

    def request_stop(self) -> None:
        """Ask the in-flight completion to stop at the next token."""
        with self._lock:
            if self._generating:
                self._cancel_generate = True

    def _is_generate_cancelled(self) -> bool:
        with self._lock:
            return self._cancel_generate

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

    def generate(self, prompt: str, *, max_tokens: int = CHAT_MAX_TOKENS) -> str:
        """Run one completion and return text safe to show to an analyst."""
        with self._lock:
            if self._status is not RuntimeStatus.READY or self._llama is None:
                raise ModelNotReadyError(
                    "Load a local model before generating a reply."
                )
            llama = self._llama
        raw = self._complete(
            llama,
            prompt,
            max_tokens=max_tokens,
            should_stop=self._is_generate_cancelled,
        )
        cleaned = strip_reasoning_tags(raw)
        if self._is_generate_cancelled():
            return cleaned if cleaned else STOPPED_NOTICE
        return cleaned if cleaned else EMPTY_REPLY_NOTICE

    def start_generate(self, prompt: str, *, max_tokens: int = CHAT_MAX_TOKENS) -> None:
        """Begin a background completion so the Streamlit script can return."""
        with self._lock:
            if self._generating or self._titling:
                return
            if self._status is not RuntimeStatus.READY or self._llama is None:
                self._reply_error = "Load a local model before generating a reply."
                self._last_reply = None
                return
            self._generating = True
            self._cancel_generate = False
            self._generate_started_at = time.monotonic()
            self._last_generate_seconds = None
            self._last_reply = None
            self._reply_error = None
        worker = threading.Thread(
            target=self._generate_worker,
            args=(prompt, max_tokens),
            name="localgridmind-gguf-generate",
            daemon=True,
        )
        worker.start()

    def start_title_generate(
        self, prompt: str, *, max_tokens: int = TITLE_MAX_TOKENS
    ) -> None:
        """Hidden title completion. Does not replace last_reply or chat status."""
        with self._lock:
            if self._generating or self._titling:
                return
            if self._status is not RuntimeStatus.READY or self._llama is None:
                self._title_error = "Load a local model before generating a title."
                self._last_title = None
                return
            self._titling = True
            self._last_title = None
            self._title_error = None
        worker = threading.Thread(
            target=self._title_worker,
            args=(prompt, max_tokens),
            name="localgridmind-gguf-title",
            daemon=True,
        )
        worker.start()

    def _generate_worker(self, prompt: str, max_tokens: int) -> None:
        try:
            reply = self.generate(prompt, max_tokens=max_tokens)
        except Exception as exc:
            with self._lock:
                self._finish_generate_locked(
                    reply=None,
                    error=str(exc) or exc.__class__.__name__,
                )
            return
        with self._lock:
            self._finish_generate_locked(reply=reply, error=None)

    def _finish_generate_locked(
        self, *, reply: str | None, error: str | None
    ) -> None:
        started = self._generate_started_at
        if started is not None:
            self._last_generate_seconds = max(0.0, time.monotonic() - started)
        self._generating = False
        self._generate_started_at = None
        self._last_reply = reply
        self._reply_error = error

    def _title_worker(self, prompt: str, max_tokens: int) -> None:
        try:
            with self._lock:
                if self._status is not RuntimeStatus.READY or self._llama is None:
                    raise ModelNotReadyError(
                        "Load a local model before generating a title."
                    )
                llama = self._llama
            raw = self._complete(llama, prompt, max_tokens=max_tokens)
            cleaned = strip_reasoning_tags(raw)
        except Exception as exc:
            with self._lock:
                self._titling = False
                self._last_title = None
                self._title_error = str(exc) or exc.__class__.__name__
            return
        with self._lock:
            self._titling = False
            self._last_title = cleaned
            self._title_error = None

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
        self._last_generate_seconds = None
        self._last_reply = None
        self._reply_error = None
        self._cancel_generate = False
        self._titling = False
        self._last_title = None
        self._title_error = None
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
    def _stopping_criteria(should_stop: Callable[[], bool] | None) -> Any:
        if should_stop is None:
            return None

        def _criteria(_tokens: Any, _logits: Any) -> bool:
            return bool(should_stop())

        try:
            from llama_cpp import StoppingCriteriaList

            return StoppingCriteriaList([_criteria])
        except ImportError:
            return [_criteria]

    @staticmethod
    def _content_from_choice(choice: dict[str, Any]) -> str:
        message = choice.get("message") or {}
        content = message.get("content")
        if content:
            return str(content)
        delta = choice.get("delta") or {}
        delta_content = delta.get("content")
        if delta_content:
            return str(delta_content)
        text = choice.get("text")
        if text:
            return str(text)
        return ""

    @classmethod
    def _read_completion(
        cls,
        result: Any,
        *,
        should_stop: Callable[[], bool] | None,
    ) -> str:
        if result is None:
            return ""
        if isinstance(result, dict):
            choices = result.get("choices") or []
            if not choices:
                return ""
            return cls._content_from_choice(choices[0])
        parts: list[str] = []
        try:
            for chunk in result:
                if should_stop is not None and should_stop():
                    break
                if not isinstance(chunk, dict):
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                piece = cls._content_from_choice(choices[0])
                if piece:
                    parts.append(piece)
        finally:
            close = getattr(result, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        return "".join(parts)

    @classmethod
    def _complete(
        cls,
        llama: Any,
        prompt: str,
        *,
        max_tokens: int,
        should_stop: Callable[[], bool] | None = None,
    ) -> str:
        # create_chat_completion has no stopping_criteria (llama-cpp-python
        # 0.3.x). Abort by streaming and closing the iterator on Stop.
        if hasattr(llama, "create_chat_completion"):
            kwargs: dict[str, Any] = {
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": True,
            }
            try:
                result = llama.create_chat_completion(**kwargs)
            except TypeError:
                kwargs.pop("stream", None)
                result = llama.create_chat_completion(**kwargs)
            return cls._read_completion(result, should_stop=should_stop)

        stop_arg = cls._stopping_criteria(should_stop)
        kwargs = {
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "echo": False,
            "stream": True,
        }
        if stop_arg is not None:
            kwargs["stopping_criteria"] = stop_arg
        try:
            result = llama(prompt, **kwargs)
        except TypeError:
            kwargs.pop("stream", None)
            result = llama(prompt, **kwargs)
        return cls._read_completion(result, should_stop=should_stop)


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
