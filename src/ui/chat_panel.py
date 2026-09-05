"""ChatGPT / Gemini-like thread: user right, assistant left, input pinned."""

from __future__ import annotations

import html

import streamlit as st

from llm.runtime import get_runtime
from ui.chat_store import (
    AWAITING_KEY,
    THREAD_KEY,
    add_message,
    empty_thread,
    format_message_stamp,
)

def ensure_thread() -> list[dict]:
    if THREAD_KEY not in st.session_state:
        st.session_state[THREAD_KEY] = empty_thread()
    if AWAITING_KEY not in st.session_state:
        st.session_state[AWAITING_KEY] = False
    return st.session_state[THREAD_KEY]


def clear_thread() -> None:
    st.session_state[THREAD_KEY] = empty_thread()
    st.session_state[AWAITING_KEY] = False


def render_chat_shell(*, model_ready: bool) -> None:
    """History (scrollable) plus a bottom-pinned chat input."""
    thread = ensure_thread()
    _ingest_finished_reply(thread)

    for message in thread:
        _render_turn(message)

    runtime = get_runtime()
    if runtime.is_generating:
        total = max(0, int(runtime.generate_elapsed_seconds))
        minutes, rest = divmod(total, 60)
        elapsed = f"{rest} s" if minutes == 0 else f"{minutes} min {rest:02d} s"
        st.caption(
            f"Generating a reply… Elapsed {elapsed}. "
            "This can take one or two minutes on this computer."
        )
    busy = runtime.is_generating or not model_ready
    placeholder = (
        "Ask a question"
        if model_ready
        else "Load a local model to start"
    )
    prompt = st.chat_input(placeholder, disabled=busy)
    if prompt and model_ready and not runtime.is_generating:
        add_message(thread, "user", prompt.strip())
        runtime.start_generate(prompt.strip())
        st.session_state[AWAITING_KEY] = True
        st.rerun()


def _ingest_finished_reply(thread: list[dict]) -> None:
    runtime = get_runtime()
    if runtime.is_generating or not st.session_state.get(AWAITING_KEY):
        return
    if runtime.reply_error:
        add_message(thread, "assistant", runtime.reply_error)
    elif runtime.last_reply:
        add_message(thread, "assistant", runtime.last_reply)
    st.session_state[AWAITING_KEY] = False


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
    st.markdown(f'<div class="lgm-turn lgm-assistant">', unsafe_allow_html=True)
    st.markdown(content)
    st.markdown("</div>", unsafe_allow_html=True)
