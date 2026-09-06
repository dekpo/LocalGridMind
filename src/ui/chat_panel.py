"""ChatGPT / Gemini-like thread: user right, assistant left, input pinned."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st

from config import UPLOADS_DIR
from core.lookup import answer_from_json, answer_inventory_question
from core.packs import (
    NoWorkbookFilesError,
    attach_uploads_to_conversation,
    uploads_from_files,
)
from core.prompt import build_chat_prompt
from llm.runtime import (
    RuntimeStatus,
    get_runtime,
    is_retryable_notice,
)
from ui.chat_store import (
    AUTO_TITLE_DONE_KEY,
    AWAITING_KEY,
    AWAITING_TITLE_KEY,
    CONVERSATION_ID_KEY,
    FOLDER_UPLOAD_NONCE_KEY,
    PACK_ATTACH_ERROR_KEY,
    THREAD_KEY,
    TITLE_CONVERSATION_ID_KEY,
    add_message,
    empty_thread,
    format_elapsed_label,
    format_generated_in,
    format_message_stamp,
    generating_wait_copy,
    last_user_content,
)
from ui.library import (
    ConversationLibrary,
    build_title_prompt,
    heuristic_title,
    sanitize_model_title,
)
from ui.reply_ingest import ingest_finished_reply

WORKBOOK_TYPES = ["xlsx", "xlsm", "csv"]
NEED_MODEL_NOTICE = (
    "The workbook inventory is ready in this chat. "
    "Load a local model to ask a question."
)


def ensure_thread() -> list[dict]:
    if THREAD_KEY not in st.session_state:
        st.session_state[THREAD_KEY] = empty_thread()
    if AWAITING_KEY not in st.session_state:
        st.session_state[AWAITING_KEY] = False
    if AWAITING_TITLE_KEY not in st.session_state:
        st.session_state[AWAITING_TITLE_KEY] = False
    return st.session_state[THREAD_KEY]


def activate_conversation(
    library: ConversationLibrary, conversation_id: int
) -> None:
    """Load a stored thread into session state."""
    st.session_state[CONVERSATION_ID_KEY] = conversation_id
    st.session_state[THREAD_KEY] = [
        item.as_thread_item() for item in library.list_messages(conversation_id)
    ]
    st.session_state[AWAITING_KEY] = False


def ensure_active_conversation(library: ConversationLibrary) -> int:
    """Resume the latest thread, or create an empty one on first launch."""
    current = st.session_state.get(CONVERSATION_ID_KEY)
    if current is not None and library.get_conversation(current) is not None:
        ensure_thread()
        return int(current)
    recents = library.list_conversations()
    if recents:
        activate_conversation(library, recents[0].id)
        return recents[0].id
    created = library.create_conversation()
    activate_conversation(library, created.id)
    return created.id


def start_new_chat(library: ConversationLibrary) -> int:
    """Create an empty conversation and show a blank thread."""
    created = library.create_conversation()
    activate_conversation(library, created.id)
    return created.id


def clear_thread() -> None:
    st.session_state[THREAD_KEY] = empty_thread()
    st.session_state[AWAITING_KEY] = False


def render_chat_shell(
    *,
    model_ready: bool,
    library: ConversationLibrary,
    conversation_id: int,
    max_tokens: int,
) -> None:
    """History (scrollable) plus a bottom-pinned chat input."""
    thread = ensure_thread()
    _ingest_finished_reply(thread, library, conversation_id)
    _maybe_auto_title(library, conversation_id, model_ready)
    _ingest_finished_title(library)

    runtime = get_runtime()
    busy = runtime.is_generating or runtime.is_titling
    attach_error = st.session_state.pop(PACK_ATTACH_ERROR_KEY, None)
    if attach_error:
        st.error(str(attach_error))
    folder_files = _render_folder_attach(
        library, conversation_id, disabled=busy
    )
    if folder_files and not busy:
        _handle_attachment(
            thread,
            library,
            conversation_id,
            files=folder_files,
            question="",
            model_ready=model_ready,
            max_tokens=max_tokens,
        )
        st.session_state[FOLDER_UPLOAD_NONCE_KEY] = (
            int(st.session_state.get(FOLDER_UPLOAD_NONCE_KEY, 0)) + 1
        )
        st.rerun()

    for message in thread:
        _render_turn(message)

    _offer_generate_again(
        thread,
        library=library,
        conversation_id=conversation_id,
        model_ready=model_ready,
        max_tokens=max_tokens,
    )
    if runtime.is_generating:
        elapsed_s = runtime.generate_elapsed_seconds
        elapsed = format_elapsed_label(elapsed_s)
        wait = generating_wait_copy(elapsed_s)
        text_col, stop_col = st.columns([0.82, 0.18], vertical_alignment="center")
        with text_col:
            st.markdown(
                f'<div class="lgm-generating">'
                f'<span class="lgm-spinner" aria-hidden="true"></span>'
                f"<span>{html.escape(wait)} {html.escape(elapsed)}.</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with stop_col:
            stop_label = "Stopping…" if runtime.is_cancel_requested else "Stop"
            if st.button(
                stop_label,
                key="lgm-stop-generate",
                disabled=runtime.is_cancel_requested,
                use_container_width=True,
            ):
                runtime.request_stop()
                st.rerun()
    pack = library.get_conversation_pack(conversation_id)
    if model_ready:
        placeholder = "Ask a question or attach a workbook"
    elif pack is not None:
        placeholder = "Ask about this workbook, or load a local model"
    else:
        placeholder = "Attach a workbook, or load a local model to ask"
    prompt = st.chat_input(
        placeholder,
        disabled=busy,
        accept_file="multiple",
        file_type=WORKBOOK_TYPES,
    )
    if prompt and not busy:
        question, files = _submission_text_and_files(prompt)
        if files:
            _handle_attachment(
                thread,
                library,
                conversation_id,
                files=files,
                question=question,
                model_ready=model_ready,
                max_tokens=max_tokens,
            )
            st.rerun()
        elif question:
            stored = add_message(thread, "user", question)
            library.append_message(
                conversation_id,
                "user",
                stored["content"],
                created_at=stored["created_at"],
            )
            lookup = _lookup_reply(library, conversation_id, question)
            if lookup:
                _persist_assistant(thread, library, conversation_id, lookup)
            elif model_ready:
                runtime.start_generate(
                    _model_prompt(library, conversation_id, question),
                    max_tokens=max_tokens,
                )
                st.session_state[AWAITING_KEY] = True
            else:
                _persist_assistant(
                    thread, library, conversation_id, NEED_MODEL_NOTICE
                )
            st.rerun()


def _offer_generate_again(
    thread: list[dict],
    *,
    library: ConversationLibrary,
    conversation_id: int,
    model_ready: bool,
    max_tokens: int,
) -> None:
    """Offer a steered retry after a think-only or stopped reply."""
    runtime = get_runtime()
    if not model_ready or runtime.is_generating or runtime.is_titling:
        return
    if not thread:
        return
    last = thread[-1]
    if last.get("role") != "assistant":
        return
    if not is_retryable_notice(str(last.get("content") or "")):
        return
    user_text = last_user_content(thread)
    if not user_text:
        return
    if st.button("Generate again", key="lgm-generate-again"):
        runtime.start_generate(
            _model_prompt(library, conversation_id, user_text, retry=True),
            max_tokens=max_tokens,
        )
        st.session_state[AWAITING_KEY] = True
        st.rerun()


def _render_folder_attach(
    library: ConversationLibrary,
    conversation_id: int,
    *,
    disabled: bool,
) -> list[Any] | None:
    pack = library.get_conversation_pack(conversation_id)
    if pack is not None:
        names = [
            Path(item.original_name.replace("\\", "/")).name
            for item in library.list_pack_files(pack.id)
        ]
        listed = ", ".join(names) if names else pack.display_name
        st.caption(
            f"Attached in this chat: {listed}. Attach again to replace."
        )
    with st.expander("Attach a folder of linked workbooks", expanded=False):
        st.caption(
            "Use this when files look up values in other workbooks. "
            "The paperclip on the message bar attaches individual files."
        )
        nonce = int(st.session_state.setdefault(FOLDER_UPLOAD_NONCE_KEY, 0))
        uploaded = st.file_uploader(
            "Workbook folder",
            type=WORKBOOK_TYPES,
            accept_multiple_files="directory",
            disabled=disabled,
            key=f"folder_pack_{nonce}",
        )
        if uploaded:
            return list(uploaded)
    return None


def _handle_attachment(
    thread: list[dict],
    library: ConversationLibrary,
    conversation_id: int,
    *,
    files: list[Any],
    question: str,
    model_ready: bool,
    max_tokens: int,
) -> None:
    try:
        result = attach_uploads_to_conversation(
            library,
            conversation_id,
            uploads_from_files(files),
            UPLOADS_DIR,
            question=question,
        )
    except NoWorkbookFilesError:
        st.session_state[PACK_ATTACH_ERROR_KEY] = (
            "No Excel or CSV files were found in that upload."
        )
        return
    except Exception:
        st.session_state[PACK_ATTACH_ERROR_KEY] = (
            "Those workbooks could not be attached. Try saving them again from Excel."
        )
        return

    user = add_message(thread, "user", result.user_text)
    library.append_message(
        conversation_id,
        "user",
        user["content"],
        created_at=user["created_at"],
    )
    inventory = add_message(thread, "assistant", result.english_text)
    library.append_message(
        conversation_id,
        "assistant",
        inventory["content"],
        created_at=inventory["created_at"],
    )
    if not question.strip():
        return
    lookup = answer_inventory_question(question, result.inventory)
    if lookup:
        _persist_assistant(thread, library, conversation_id, lookup)
        return
    runtime = get_runtime()
    if model_ready and not runtime.is_generating and not runtime.is_titling:
        runtime.start_generate(
            _model_prompt(library, conversation_id, question),
            max_tokens=max_tokens,
        )
        st.session_state[AWAITING_KEY] = True
    elif not model_ready:
        _persist_assistant(thread, library, conversation_id, NEED_MODEL_NOTICE)


def _submission_text_and_files(prompt: Any) -> tuple[str, list[Any]]:
    if prompt is None:
        return "", []
    if isinstance(prompt, str):
        return prompt.strip(), []
    text = str(getattr(prompt, "text", "") or "").strip()
    files = getattr(prompt, "files", None)
    if files is None and isinstance(prompt, dict):
        text = str(prompt.get("text") or "").strip()
        files = prompt.get("files") or []
    return text, list(files or [])


def _lookup_reply(
    library: ConversationLibrary, conversation_id: int, question: str
) -> str | None:
    pack = library.get_conversation_pack(conversation_id)
    if pack is None:
        return None
    return answer_from_json(question, pack.inventory_json)


def _persist_assistant(
    thread: list[dict],
    library: ConversationLibrary,
    conversation_id: int,
    content: str,
) -> None:
    stored = add_message(thread, "assistant", content)
    library.append_message(
        conversation_id,
        "assistant",
        stored["content"],
        created_at=stored["created_at"],
    )


def _model_prompt(
    library: ConversationLibrary,
    conversation_id: int,
    user_text: str,
    *,
    retry: bool = False,
) -> str:
    pack = library.get_conversation_pack(conversation_id)
    inventory = pack.prompt_text if pack is not None else None
    return build_chat_prompt(user_text, inventory, retry=retry)


def _ingest_finished_reply(
    thread: list[dict],
    library: ConversationLibrary,
    conversation_id: int,
) -> None:
    runtime = get_runtime()
    ingest_finished_reply(thread, library, conversation_id, runtime)
    if not runtime.is_generating:
        st.session_state[AWAITING_KEY] = False


def _maybe_auto_title(
    library: ConversationLibrary,
    conversation_id: int,
    model_ready: bool,
) -> None:
    if st.session_state.get(AWAITING_TITLE_KEY):
        return
    done = st.session_state.setdefault(AUTO_TITLE_DONE_KEY, set())
    if conversation_id in done:
        return
    if not library.needs_auto_title(conversation_id):
        return

    first_user = library.first_user_content(conversation_id)
    interim = heuristic_title(first_user)
    current = library.get_conversation(conversation_id)
    if current is not None and interim != current.title:
        library.set_title(conversation_id, interim)
    done.add(conversation_id)

    runtime = get_runtime()
    if (
        model_ready
        and runtime.status is RuntimeStatus.READY
        and not runtime.is_generating
        and not runtime.is_titling
    ):
        runtime.start_title_generate(build_title_prompt(first_user))
        if runtime.is_titling:
            st.session_state[AWAITING_TITLE_KEY] = True
            st.session_state[TITLE_CONVERSATION_ID_KEY] = conversation_id
    st.rerun()


def _ingest_finished_title(library: ConversationLibrary) -> None:
    runtime = get_runtime()
    if runtime.is_titling or not st.session_state.get(AWAITING_TITLE_KEY):
        return
    conversation_id = st.session_state.get(TITLE_CONVERSATION_ID_KEY)
    st.session_state[AWAITING_TITLE_KEY] = False
    if conversation_id is None:
        return

    titled = sanitize_model_title(runtime.last_title or "")
    if not titled:
        first_user = library.first_user_content(int(conversation_id))
        titled = heuristic_title(first_user)
    library.set_title(int(conversation_id), titled)
    st.rerun()


def _render_turn(message: dict) -> None:
    role = message.get("role")
    content = str(message.get("content") or "")
    if role == "user":
        stamp = format_message_stamp(str(message.get("created_at") or ""))
        safe = html.escape(content).replace("\n", "<br>")
        st.markdown(
            f'<div class="lgm-turn lgm-user">'
            f'<div class="lgm-bubble">{safe}</div>'
            f'<div class="lgm-stamp">{html.escape(stamp)}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        return
    st.markdown('<div class="lgm-turn lgm-assistant">', unsafe_allow_html=True)
    st.markdown(content)
    elapsed_stamp = format_generated_in(message.get("elapsed_seconds"))
    if elapsed_stamp:
        st.markdown(
            f'<div class="lgm-stamp">{html.escape(elapsed_stamp)}</div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
