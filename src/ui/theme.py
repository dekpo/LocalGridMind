"""Load the app stylesheet from assets/css/style.css (same idea as Reporting-Tools-RAG)."""

from __future__ import annotations

from pathlib import Path

try:
    from config import PROJECT_ROOT
except ImportError:
    from src.config import PROJECT_ROOT

STYLESHEET_PATH = PROJECT_ROOT / "assets" / "css" / "style.css"


def apply_theme(stylesheet: Path | None = None) -> None:
    """Inject the project CSS once after st.set_page_config()."""
    import streamlit as st

    path = stylesheet if stylesheet is not None else STYLESHEET_PATH
    if not path.is_file():
        return
    css = path.read_text(encoding="utf-8")
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)
