"""Sidebar model controls and the Phase 1 smoke-test pane."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from llm.runtime import SMOKE_PROMPT, RuntimeStatus, get_runtime

_STATUS_POLL_SECONDS = 1.0

_STATUS_LABELS = {
    RuntimeStatus.UNLOADED: "Unloaded",
    RuntimeStatus.LOADING: "Loading",
    RuntimeStatus.READY: "Ready",
    RuntimeStatus.ERROR: "Error",
}


def render_model_sidebar(selected_path: Path | None) -> None:
    """Load / unload controls and English runtime status for the sidebar."""
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

    st.session_state["_sidebar_selected_path"] = selected_path
    # Re-read after the click: the snapshot above is stale on the Load run.
    if get_runtime().status is RuntimeStatus.LOADING:
        _status_while_loading()
    else:
        _status_idle()


@st.fragment(run_every=_STATUS_POLL_SECONDS)
def _status_while_loading() -> None:
    _render_status(st.session_state.get("_sidebar_selected_path"))
    if get_runtime().status is not RuntimeStatus.LOADING:
        st.rerun()


@st.fragment
def _status_idle() -> None:
    _render_status(st.session_state.get("_sidebar_selected_path"))


def render_smoke_test(selected_path: Path | None) -> None:
    """One-prompt generate check in the main pane."""
    runtime = get_runtime()
    st.subheader("Model check")
    st.caption(
        "Send one short message to confirm the local model replies. "
        "Workbook analysis is added in a later step."
    )

    if "smoke_prompt" not in st.session_state:
        st.session_state["smoke_prompt"] = SMOKE_PROMPT

    prompt = st.text_area(
        "Test message",
        key="smoke_prompt",
        height=100,
    )
    busy = runtime.status is RuntimeStatus.LOADING or runtime.is_generating
    generate_disabled = selected_path is None or busy or not runtime.is_ready()
    if st.button("Generate", key="smoke_generate", disabled=generate_disabled):
        runtime.start_generate(prompt)
        st.session_state["_smoke_busy"] = True
        st.rerun()

    # Always the same fragment. It draws generating *or* the reply on each
    # tick, so a finished job does not wait for a full-page rerun / focus.
    _smoke_output()


@st.fragment(run_every=_STATUS_POLL_SECONDS)
def _smoke_output() -> None:
    runtime = get_runtime()
    if runtime.is_generating:
        st.session_state["_smoke_busy"] = True
        elapsed = _format_elapsed(runtime.generate_elapsed_seconds)
        st.info(
            f"Generating a reply… Elapsed {elapsed}. "
            "This can take one or two minutes on this computer. "
            "You do not need to click the text box."
        )
        return

    if runtime.reply_error:
        st.error(runtime.reply_error)
    elif runtime.last_reply:
        st.markdown("**Reply**")
        st.write(runtime.last_reply)
    elif runtime.is_ready():
        st.caption("The model is ready. Generate a reply when you want to check it.")

    if st.session_state.get("_smoke_busy"):
        st.session_state["_smoke_busy"] = False
        st.rerun()


def _render_status(selected_path: Path | None) -> None:
    runtime = get_runtime()
    status = runtime.status
    label = _STATUS_LABELS[status]
    loaded = runtime.loaded_path

    if status is RuntimeStatus.LOADING:
        elapsed = _format_elapsed(runtime.load_elapsed_seconds)
        progress = runtime.load_progress
        if progress is None:
            shown = 0.0
            detail = f"{label}: starting. Elapsed {elapsed}."
        elif progress <= 0.0:
            shown = 0.0
            detail = (
                f"{label}: starting the model engine. "
                f"Elapsed {elapsed}. The bar stays at 0% until Windows allows it."
            )
        elif progress < 1.0:
            shown = progress
            detail = f"{label}: {int(progress * 100)}%. Elapsed {elapsed}."
        else:
            shown = 1.0
            detail = (
                f"{label}: finishing in memory. Elapsed {elapsed}. "
                "This last step can still take a few minutes."
            )
        st.progress(shown)
        st.warning(
            f"{detail} The first open can take several minutes on this computer. "
            "If the elapsed time keeps changing, the app is still working. "
            "You do not need to refresh the page."
        )
        return

    if status is RuntimeStatus.READY:
        name = loaded.stem if loaded is not None else "model"
        st.success(f"{label}: {name}")
        if selected_path is not None and loaded is not None and selected_path != loaded:
            st.info(
                "A different model is selected. Load it to switch. "
                "The current model is unloaded first so memory stays free."
            )
        return

    if status is RuntimeStatus.ERROR:
        detail = runtime.error_message or "The model file could not be opened."
        st.error(f"{label}: {detail}")
        return

    st.info(f"{label}: no model is in memory. Choose a file and load it.")


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, rest = divmod(total, 60)
    if minutes == 0:
        return f"{rest} s"
    return f"{minutes} min {rest:02d} s"
