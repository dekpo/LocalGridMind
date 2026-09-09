"""Embeddable CPython ._pth helper. No download."""

from pathlib import Path

from tools.portable.enable_embed_site import enable_embed_site


def test_enable_embed_site_uncomments_import_site(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    pth = runtime / "python313._pth"
    pth.write_text("python313.zip\n.\n#import site\n", encoding="utf-8")

    enable_embed_site(runtime)

    text = pth.read_text(encoding="utf-8")
    assert "import site" in text
    assert "#import site" not in text
    assert "Lib/site-packages" in text
    assert (runtime / "Lib" / "site-packages").is_dir()
