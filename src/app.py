"""Streamlit entry: local model controls and a ChatGPT-like chat shell."""

from __future__ import annotations

import time

import streamlit as st

from config import (
    N_THREADS,
    ensure_runtime_directories,
    get_model_labels,
    resolve_model_by_label,
)
from llm.runtime import RuntimeStatus, get_runtime
from ui.chat_panel import clear_thread, render_chat_shell
from ui.runtime_panel import render_model_sidebar
from ui.theme import apply_theme

st.set_page_config(page_title="LocalGridMind", layout="wide")
ensure_runtime_directories()
apply_theme()

st.title("LocalGridMind")
st.caption(
    "Private desktop analysis for complex Excel and CSV workbooks. "
    "Ask in the thread below. Files stay on this machine."
)

model_labels = get_model_labels()
selected_model = None
runtime = get_runtime()

with st.sidebar:
    if st.button("New chat", use_container_width=True, disabled=runtime.is_generating):
        clear_thread()
        st.rerun()

    with st.expander("Local model", expanded=True):
        st.caption(f"CPU threads locked to {N_THREADS}.")
        if model_labels:
            selected_label = st.selectbox("Active GGUF model", options=model_labels)
            selected_model = resolve_model_by_label(selected_label)
            render_model_sidebar(selected_model.path if selected_model else None)
        else:
            st.warning(
                "No local model file found. Place one in the models folder, then refresh."
            )
            render_model_sidebar(None)

model_ready = selected_model is not None and runtime.status is RuntimeStatus.READY
render_chat_shell(model_ready=model_ready)

# Full-script poll. Fragments on Windows leave ghost status boxes and can
# freeze the percent until a manual refresh. One rerun per second is enough.
if runtime.status is RuntimeStatus.LOADING or runtime.is_generating:
    time.sleep(1.0)
    st.rerun()
