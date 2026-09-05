"""Runtime tests that never open a real GGUF file."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from src.config import CHAT_MAX_TOKENS, N_BATCH, N_CTX, N_GPU_LAYERS, N_THREADS
from src.llm.runtime import (
    EMPTY_REPLY_NOTICE,
    RETRY_STEER_PREFIX,
    STOPPED_NOTICE,
    ModelNotReadyError,
    ModelRuntime,
    RuntimeStatus,
    build_retry_prompt,
    explain_load_error,
    get_runtime,
    is_retryable_notice,
    reset_runtime_for_tests,
    strip_reasoning_tags,
)


class FakeLlama:
    """Stand-in for llama_cpp.Llama. Records constructor kwargs only."""

    instances: list[FakeLlama] = []

    def __init__(self, model_path: str, **kwargs: Any) -> None:
        self.model_path = model_path
        self.kwargs = kwargs
        self.closed = False
        self.prompt: str | None = None
        self.complete_kwargs: dict[str, Any] = {}
        FakeLlama.instances.append(self)

    def create_chat_completion(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.prompt = messages[0]["content"]
        self.complete_kwargs = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": "Ready. <think>hidden scratch work</think> The model is ready."
                    }
                }
            ]
        }

    def close(self) -> None:
        self.closed = True


class ExplodingLlama:
    def __init__(self, model_path: str, **kwargs: Any) -> None:
        raise OSError("simulated load failure")


@pytest.fixture(autouse=True)
def _isolate_runtime() -> None:
    FakeLlama.instances = []
    reset_runtime_for_tests()
    yield
    reset_runtime_for_tests()


def test_importing_runtime_does_not_load_a_model() -> None:
    runtime = get_runtime()
    assert runtime.status is RuntimeStatus.UNLOADED
    assert runtime.loaded_path is None
    assert FakeLlama.instances == []


def test_strip_reasoning_tags_removes_think_blocks() -> None:
    raw = "Hello <think>internal plan</think> world"
    assert strip_reasoning_tags(raw) == "Hello  world"


def test_strip_reasoning_tags_drops_unclosed_think() -> None:
    raw = "Visible <think>still reasoning"
    assert strip_reasoning_tags(raw) == "Visible"


def test_load_uses_cpu_lock_and_does_not_raise_threads(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=FakeLlama)
    runtime.load(model)

    assert runtime.status is RuntimeStatus.READY
    assert len(FakeLlama.instances) == 1
    kwargs = FakeLlama.instances[0].kwargs
    assert kwargs["n_threads"] == N_THREADS == 4
    assert kwargs["n_gpu_layers"] == N_GPU_LAYERS == 0
    assert kwargs["n_ctx"] == N_CTX
    assert kwargs["n_batch"] == N_BATCH


def test_unload_releases_model(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=FakeLlama)
    runtime.load(model)
    llama = FakeLlama.instances[0]

    runtime.unload()

    assert runtime.status is RuntimeStatus.UNLOADED
    assert runtime.loaded_path is None
    assert llama.closed is True


def test_switching_models_unloads_the_previous_one(tmp_path: Path) -> None:
    first = tmp_path / "first.gguf"
    second = tmp_path / "second.gguf"
    runtime = ModelRuntime(llama_factory=FakeLlama)

    runtime.load(first)
    first_llama = FakeLlama.instances[0]
    runtime.load(second)

    assert first_llama.closed is True
    assert runtime.loaded_path == second
    assert runtime.status is RuntimeStatus.READY
    assert len(FakeLlama.instances) == 2


def test_generate_strips_think_tags(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=FakeLlama)
    runtime.load(model)

    reply = runtime.generate("ping")

    assert "<think>" not in reply
    assert "hidden scratch work" not in reply
    assert "The model is ready." in reply
    assert FakeLlama.instances[0].prompt == "ping"
    assert FakeLlama.instances[0].complete_kwargs["max_tokens"] == CHAT_MAX_TOKENS == 1536


def test_generate_before_load_raises() -> None:
    runtime = ModelRuntime(llama_factory=FakeLlama)
    with pytest.raises(ModelNotReadyError):
        runtime.generate("ping")


def test_explain_load_error_maps_windows_4551() -> None:
    exc = OSError(
        "Failed to load shared library 'C:\\\\app\\\\.venv\\\\llama.dll': "
        "[WinError 4551] Une stratégie de contrôle d’application a bloqué ce fichier"
    )
    exc.winerror = 4551
    message = explain_load_error(exc)
    assert "4551" in message
    assert "Windows" in message
    assert "llama.dll" in message
    assert "model file" in message


def test_load_error_sets_status(tmp_path: Path) -> None:
    model = tmp_path / "broken.gguf"
    runtime = ModelRuntime(llama_factory=ExplodingLlama)
    runtime.load(model)

    assert runtime.status is RuntimeStatus.ERROR
    assert runtime.error_message is not None
    assert "simulated load failure" in runtime.error_message


class ProgressFakeLlama(FakeLlama):
    def __init__(self, model_path: str, **kwargs: Any) -> None:
        hook = kwargs.pop("progress_hook", None)
        super().__init__(model_path, **kwargs)
        if hook is not None:
            hook(0.25)
            hook(0.8)
            hook(1.0)


def test_load_progress_updates_from_hook(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=ProgressFakeLlama)
    runtime.load(model)
    assert runtime.status is RuntimeStatus.READY
    assert runtime.load_progress == 1.0


class ThinkOnlyFakeLlama(FakeLlama):
    def create_chat_completion(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.prompt = messages[0]["content"]
        return {
            "choices": [
                {"message": {"content": "<think>only hidden reasoning</think>"}}
            ]
        }


def test_generate_empty_after_think_uses_notice(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=ThinkOnlyFakeLlama)
    runtime.load(model)
    assert runtime.generate("ping") == EMPTY_REPLY_NOTICE
    assert "used all its time preparing" in EMPTY_REPLY_NOTICE


def _criteria_says_stop(criteria: Any) -> bool:
    if criteria is None:
        return False
    if callable(criteria):
        return bool(criteria([], None))
    for item in criteria:
        if callable(item) and item([], None):
            return True
    return False


class CancellableFakeLlama(FakeLlama):
    def create_chat_completion(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.prompt = messages[0]["content"]
        self.complete_kwargs = kwargs
        criteria = kwargs.get("stopping_criteria")
        for _ in range(200):
            if _criteria_says_stop(criteria):
                return {
                    "choices": [{"message": {"content": "<think>partial only"}}]
                }
            time.sleep(0.01)
        return {"choices": [{"message": {"content": "too late"}}]}


def test_request_stop_returns_stopped_notice(tmp_path: Path) -> None:
    import time

    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=CancellableFakeLlama)
    runtime.load(model)
    runtime.start_generate("long think")
    for _ in range(50):
        if runtime.is_generating:
            break
        time.sleep(0.01)
    runtime.request_stop()
    for _ in range(100):
        if not runtime.is_generating and runtime.last_reply is not None:
            break
        time.sleep(0.01)
    assert runtime.is_generating is False
    assert runtime.last_reply == STOPPED_NOTICE
    assert is_retryable_notice(STOPPED_NOTICE)
    assert is_retryable_notice(EMPTY_REPLY_NOTICE)


def test_build_retry_prompt_steers_toward_a_visible_answer() -> None:
    steered = build_retry_prompt("How do I meditate?")
    assert steered.startswith(RETRY_STEER_PREFIX)
    assert steered.endswith("How do I meditate?")
    assert "Keep hidden reasoning very short" in steered


def test_start_generate_stores_reply(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=FakeLlama)
    runtime.load(model)
    runtime.start_generate("ping")
    import time

    for _ in range(50):
        if runtime.last_reply is not None:
            break
        time.sleep(0.01)
    assert runtime.is_generating is False
    assert runtime.last_reply is not None
    assert "The model is ready." in runtime.last_reply
    assert runtime.last_generate_seconds is not None
    assert runtime.last_generate_seconds >= 0.0


def test_start_title_generate_does_not_replace_last_reply(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=FakeLlama)
    runtime.load(model)
    runtime.start_generate("ping")
    import time

    for _ in range(50):
        if runtime.last_reply is not None:
            break
        time.sleep(0.01)
    chat_reply = runtime.last_reply

    runtime.start_title_generate("title this")
    for _ in range(50):
        if runtime.last_title is not None:
            break
        time.sleep(0.01)

    assert runtime.is_titling is False
    assert runtime.last_title is not None
    assert "<think>" not in runtime.last_title
    assert runtime.last_reply == chat_reply
    assert FakeLlama.instances[0].prompt == "title this"


def test_start_load_is_lazy_until_called(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=FakeLlama)
    assert runtime.status is RuntimeStatus.UNLOADED
    runtime.start_load(model)
    # FakeLlama is synchronous inside the worker; join by polling status.
    for _ in range(50):
        if runtime.status is RuntimeStatus.READY:
            break
        import time

        time.sleep(0.01)
    assert runtime.status is RuntimeStatus.READY
    assert len(FakeLlama.instances) == 1
