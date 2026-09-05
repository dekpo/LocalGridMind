"""Minimal Streamlit entry point: local GGUF runtime and English UI shell."""

from __future__ import annotations

import streamlit as st

from config import (
    MODELS_DIR,
    N_THREADS,
    ensure_runtime_directories,
    get_model_labels,
    resolve_model_by_label,
)
from ui.runtime_panel import render_model_sidebar, render_smoke_test

st.set_page_config(page_title="LocalGridMind", layout="wide")
ensure_runtime_directories()

st.title("LocalGridMind")
st.caption(
    "Private desktop analysis for complex Excel and CSV workbooks. "
    "Extract data and spreadsheet logic without sending files off this machine."
)

model_labels = get_model_labels()
selected_model = None

with st.sidebar:
    st.header("Local model")
    st.caption(f"CPU threads locked to {N_THREADS}. Models folder: `{MODELS_DIR}`.")
    if model_labels:
        selected_label = st.selectbox("Active GGUF model", options=model_labels)
        selected_model = resolve_model_by_label(selected_label)
        if selected_model is not None:
            st.code(str(selected_model.path), language="text")
        render_model_sidebar(selected_model.path if selected_model else None)
    else:
        st.warning(
            "No `.gguf` file found in `models/`. "
            "Download a quantized model and drop it there, then refresh."
        )
        render_model_sidebar(None)

st.info(
    "File loading, formula extraction, and cleaner exports land in later phases. "
    "This screen confirms that a local model can load and reply."
)

if selected_model is not None:
    render_smoke_test(selected_model.path)
else:
    st.caption("Add a local model file to run the short readiness check.")
