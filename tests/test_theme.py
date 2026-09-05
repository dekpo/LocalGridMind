"""Theme file lives next to the app so CSS is not buried in Python."""

from src.ui.theme import STYLESHEET_PATH


def test_stylesheet_is_present_and_readable() -> None:
    assert STYLESHEET_PATH.is_file()
    text = STYLESHEET_PATH.read_text(encoding="utf-8")
    assert ":root" in text
    assert "lgm-bubble" in text
    assert "lgm-spinner" in text
    assert "#lgm-model-ready" in text
