"""Streamlit entry: local model controls and a ChatGPT-like chat shell."""

from __future__ import annotations

import time

import streamlit as st

from config import (
    CHATS_DB_PATH,
    DEFAULT_REASONING_TIME_LABEL,
    N_THREADS,
    REASONING_TIME_LABELS,
    UPLOADS_DIR,
    ensure_runtime_directories,
    get_model_labels,
    resolve_model_by_label,
    resolve_reasoning_tokens,
)
from core.packs import purge_orphan_pack_files
from llm.runtime import RuntimeStatus, get_runtime
from ui.chat_panel import (
    activate_conversation,
    ensure_active_conversation,
    render_chat_shell,
    start_new_chat,
)
from ui.library import ConversationLibrary
from ui.recents_panel import render_recents_sidebar
from ui.runtime_panel import render_model_sidebar
from ui.theme import apply_theme

REASONING_TIME_KEY = "reasoning_time_label"

st.set_page_config(page_title="LocalGridMind", layout="wide")
ensure_runtime_directories()
apply_theme()

st.title("LocalGridMind")
st.caption(
    "Private desktop analysis for complex Excel and CSV workbooks. "
    "Ask in the thread below. Files stay on this machine."
)

library = ConversationLibrary(CHATS_DB_PATH)
conversation_id = ensure_active_conversation(library)

model_labels = get_model_labels()
selected_model = None
runtime = get_runtime()
sidebar_busy = runtime.is_generating or runtime.is_titling
model_selects_busy = (
    sidebar_busy or runtime.status is RuntimeStatus.LOADING
)
if REASONING_TIME_KEY not in st.session_state:
    st.session_state[REASONING_TIME_KEY] = DEFAULT_REASONING_TIME_LABEL

with st.sidebar:
    if st.button("New chat", use_container_width=True, disabled=sidebar_busy):
        start_new_chat(library)
        st.rerun()

    recents = render_recents_sidebar(library, disabled=sidebar_busy)
    if recents.deleted_id is not None:
        try:
            library.delete_conversation(recents.deleted_id)
            purge_orphan_pack_files(library, UPLOADS_DIR)
        except KeyError:
            pass
        if recents.deleted_id == conversation_id:
            leftover = library.list_conversations()
            if leftover:
                activate_conversation(library, leftover[0].id)
            else:
                start_new_chat(library)
        st.rerun()
    if recents.opened_id is not None and recents.opened_id != conversation_id:
        activate_conversation(library, recents.opened_id)
        st.rerun()

    with st.expander("Local model", expanded=True):
        st.caption(f"CPU threads locked to {N_THREADS}.")
        if model_labels:
            selected_label = st.selectbox(
                "Selected model",
                options=model_labels,
                disabled=model_selects_busy,
            )
            selected_model = resolve_model_by_label(selected_label)
            st.selectbox(
                "Reasoning time",
                options=list(REASONING_TIME_LABELS),
                key=REASONING_TIME_KEY,
                disabled=model_selects_busy,
            )
            render_model_sidebar(selected_model.path if selected_model else None)
        else:
            st.warning(
                "No local model file found. Place one in the models folder, then refresh."
            )
            render_model_sidebar(None)

chat_max_tokens = resolve_reasoning_tokens(
    str(st.session_state.get(REASONING_TIME_KEY, DEFAULT_REASONING_TIME_LABEL))
)
model_ready = selected_model is not None and runtime.status is RuntimeStatus.READY
render_chat_shell(
    model_ready=model_ready,
    library=library,
    conversation_id=conversation_id,
    max_tokens=chat_max_tokens,
)

# Full-script poll. Fragments on Windows leave ghost status boxes and can
# freeze the percent until a manual refresh. One rerun per second is enough.
if runtime.status is RuntimeStatus.LOADING or runtime.is_generating or runtime.is_titling:
    time.sleep(1.0)
    st.rerun()
