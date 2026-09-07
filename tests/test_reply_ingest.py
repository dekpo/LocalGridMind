"""Finished-reply ingest without Streamlit. No GGUF."""

from __future__ import annotations

from pathlib import Path

from src.core.inventory import build_pack_inventory
from src.llm.runtime import EMPTY_REPLY_NOTICE, ModelRuntime
from src.ui.chat_store import add_message, empty_thread
from src.ui.library import ConversationLibrary
from src.ui.reply_ingest import ingest_finished_reply
from tests.workbook_fixtures import write_wacc_pack_xlsx


class _IdleRuntime:
    def __init__(
        self,
        *,
        reply: str | None = None,
        error: str | None = None,
        elapsed: float | None = 1.5,
        generating: bool = False,
    ) -> None:
        self._reply = reply
        self._error = error
        self._elapsed = elapsed
        self.is_generating = generating

    def consume_finished_reply(self) -> tuple[str | None, float | None]:
        if self.is_generating:
            return None, None
        content = self._error or self._reply
        self._reply = None
        self._error = None
        if not content:
            return None, None
        return content, self._elapsed


def test_ingest_persists_finished_reply_without_awaiting_flag(
    tmp_path: Path,
) -> None:
    library = ConversationLibrary(tmp_path / "library.sqlite")
    conversation = library.create_conversation()
    thread = empty_thread()
    add_message(thread, "user", "Where is WACC?")
    runtime = _IdleRuntime(reply="Input sheet!B35 points at Cost of capital!B13.")

    stored = ingest_finished_reply(thread, library, conversation.id, runtime)

    assert stored is not None
    assert stored["role"] == "assistant"
    assert "B35" in stored["content"]
    assert stored["elapsed_seconds"] == 1.5
    messages = library.list_messages(conversation.id)
    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert "B35" in messages[0].content
    assert ingest_finished_reply(thread, library, conversation.id, runtime) is None


def test_ingest_keeps_empty_notice_and_skips_duplicates(tmp_path: Path) -> None:
    library = ConversationLibrary(tmp_path / "library.sqlite")
    conversation = library.create_conversation()
    thread = empty_thread()
    add_message(thread, "assistant", EMPTY_REPLY_NOTICE)
    runtime = _IdleRuntime(reply=EMPTY_REPLY_NOTICE)

    assert ingest_finished_reply(thread, library, conversation.id, runtime) is None
    assert library.list_messages(conversation.id) == []


def test_ingest_skips_while_generating(tmp_path: Path) -> None:
    library = ConversationLibrary(tmp_path / "library.sqlite")
    conversation = library.create_conversation()
    thread = empty_thread()
    runtime = _IdleRuntime(reply="done", generating=True)
    assert ingest_finished_reply(thread, library, conversation.id, runtime) is None
    assert thread == []


def test_consume_finished_reply_clears_runtime_slot(tmp_path: Path) -> None:
    model = tmp_path / "demo.gguf"
    runtime = ModelRuntime(llama_factory=_FinishLlama)
    runtime.load(model)
    runtime.start_generate("ping")
    for _ in range(50):
        if runtime.last_reply is not None:
            break
        import time

        time.sleep(0.01)
    assert runtime.last_reply is not None
    content, elapsed = runtime.consume_finished_reply()
    assert content
    assert elapsed is not None
    assert runtime.last_reply is None
    assert runtime.reply_error is None
    assert runtime.consume_finished_reply() == (None, None)


def test_ingest_appends_inventory_correction_when_pack_is_attached(
    tmp_path: Path,
) -> None:
    path = write_wacc_pack_xlsx(tmp_path / "wacc_pack.xlsx")
    inventory = build_pack_inventory([path])
    library = ConversationLibrary(tmp_path / "library.sqlite")
    conversation = library.create_conversation()
    pack = library.create_pack(
        inventory.display_name(),
        inventory.to_json(),
        inventory.to_english(),
        inventory.to_prompt(),
    )
    library.replace_conversation_pack(conversation.id, pack.id)
    thread = empty_thread()
    runtime = _IdleRuntime(
        reply="Cost of capital!B13 is `=1+1` according to this draft."
    )

    stored = ingest_finished_reply(thread, library, conversation.id, runtime)

    assert stored is not None
    assert stored["content"].startswith(
        "Cost of capital!B13 is `=1+1` according to this draft."
    )
    assert "=B10*B11+B12" in stored["content"]
    assert "not `=1+1`" in stored["content"]
    messages = library.list_messages(conversation.id)
    assert messages[0].content == stored["content"]


class _FinishLlama:
    def __init__(self, model_path: str, **kwargs: object) -> None:
        self.model_path = model_path

    def create_chat_completion(self, messages: list[dict[str, str]], **kwargs: object):
        return {
            "choices": [{"message": {"content": "Quoted Input sheet!B35 only."}}]
        }

    def close(self) -> None:
        return None
