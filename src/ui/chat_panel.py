"""ChatGPT / Gemini-like thread: user right, assistant left, input pinned."""

from __future__ import annotations

import html

import streamlit as st

from llm.runtime import RuntimeStatus, get_runtime
from ui.chat_store import (
    AUTO_TITLE_DONE_KEY,
    AWAITING_KEY,
    AWAITING_TITLE_KEY,
    CONVERSATION_ID_KEY,
    THREAD_KEY,
    TITLE_CONVERSATION_ID_KEY,
    add_message,
    empty_thread,
    format_elapsed_label,
    format_generated_in,
    format_message_stamp,
)
from ui.library import (
    ConversationLibrary,
    build_title_prompt,
    heuristic_title,
    sanitize_model_title,
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
) -> None:
    """History (scrollable) plus a bottom-pinned chat input."""
    thread = ensure_thread()
    _ingest_finished_reply(thread, library, conversation_id)
    _maybe_auto_title(library, conversation_id, model_ready)
    _ingest_finished_title(library)

    for message in thread:
        _render_turn(message)

    runtime = get_runtime()
    if runtime.is_generating:
        elapsed = format_elapsed_label(runtime.generate_elapsed_seconds)
        st.markdown(
            f'<div class="lgm-generating">'
            f'<span class="lgm-spinner" aria-hidden="true"></span>'
            f"<span>Generating a reply… {html.escape(elapsed)}. "
            "This can take one or two minutes on this computer.</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    busy = runtime.is_generating or runtime.is_titling or not model_ready
    placeholder = (
        "Ask a question"
        if model_ready
        else "Load a local model to start"
    )
    prompt = st.chat_input(placeholder, disabled=busy)
    if prompt and model_ready and not runtime.is_generating and not runtime.is_titling:
        stored = add_message(thread, "user", prompt.strip())
        library.append_message(
            conversation_id,
            "user",
            stored["content"],
            created_at=stored["created_at"],
        )
        runtime.start_generate(prompt.strip())
        st.session_state[AWAITING_KEY] = True
        st.rerun()


def _ingest_finished_reply(
    thread: list[dict],
    library: ConversationLibrary,
    conversation_id: int,
) -> None:
    runtime = get_runtime()
    if runtime.is_generating or not st.session_state.get(AWAITING_KEY):
        return
    stored = None
    elapsed = runtime.last_generate_seconds
    if runtime.reply_error:
        stored = add_message(
            thread, "assistant", runtime.reply_error, elapsed_seconds=elapsed
        )
    elif runtime.last_reply:
        stored = add_message(
            thread, "assistant", runtime.last_reply, elapsed_seconds=elapsed
        )
    if stored is not None:
        library.append_message(
            conversation_id,
            "assistant",
            stored["content"],
            created_at=stored["created_at"],
            elapsed_seconds=elapsed,
        )
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
