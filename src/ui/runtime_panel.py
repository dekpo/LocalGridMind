"""Sidebar local-model load / unload controls. No Streamlit fragments."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from llm.runtime import RuntimeStatus, get_runtime

_STATUS_LABELS = {
    RuntimeStatus.UNLOADED: "Unloaded",
    RuntimeStatus.LOADING: "Loading",
    RuntimeStatus.READY: "Ready",
    RuntimeStatus.ERROR: "Error",
}


def render_model_sidebar(selected_path: Path | None) -> None:
    """Load / unload buttons and one status box from the live runtime."""
    runtime = get_runtime()
    status = runtime.status
    loading = status is RuntimeStatus.LOADING

    load_disabled = selected_path is None or loading
    if st.button("Load model", disabled=load_disabled, use_container_width=True):
        if selected_path is not None:
            runtime.start_load(selected_path)
            st.rerun()

    unload_disabled = status is RuntimeStatus.UNLOADED or loading
    if st.button("Unload model", disabled=unload_disabled, use_container_width=True):
        runtime.unload()
        st.rerun()

    _render_status(selected_path)


def _render_status(selected_path: Path | None) -> None:
    # One slot so a previous Ready/Loading alert cannot linger beside the new one.
    slot = st.empty()
    with slot.container():
        _draw_status(selected_path)


def _draw_status(selected_path: Path | None) -> None:
    runtime = get_runtime()
    status = runtime.status
    label = _STATUS_LABELS[status]
    loaded = runtime.loaded_path

    if status is RuntimeStatus.LOADING:
        elapsed = _format_elapsed(runtime.load_elapsed_seconds)
        progress = runtime.load_progress
        if progress is None or progress <= 0.0:
            shown = 0.0
            detail = f"{label}: starting · {elapsed}"
        elif progress < 1.0:
            shown = progress
            detail = f"{label}: {int(progress * 100)}% · {elapsed}"
        else:
            shown = 1.0
            detail = f"{label}: finishing in memory · {elapsed}"
        st.progress(shown)
        st.warning(detail)
        return

    if status is RuntimeStatus.READY:
        name = loaded.stem if loaded is not None else "model"
        st.markdown(
            f'<div id="lgm-model-ready">{html.escape(name)}</div>',
            unsafe_allow_html=True,
        )
        if selected_path is not None and loaded is not None and selected_path != loaded:
            st.info("A different model is selected. Load it to switch.")
        return

    if status is RuntimeStatus.ERROR:
        detail = runtime.error_message or "The model file could not be opened."
        st.error(f"{label}: {detail}")
        return

    st.warning("No model in memory.")


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, rest = divmod(total, 60)
    if minutes == 0:
        return f"{rest} s"
    return f"{minutes} min {rest:02d} s"
