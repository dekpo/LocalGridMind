# -*- mode: python ; coding: utf-8 -*-
"""Thin onedir launcher. Do not collect Streamlit or llama_cpp."""

from pathlib import Path

SPEC_DIR = Path(SPEC).resolve().parent
REPO_ROOT = SPEC_DIR.parent.parent

a = Analysis(
    [str(SPEC_DIR / "launcher.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pkg_resources", "streamlit", "llama_cpp", "pandas", "plotly"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalGridMind",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LocalGridMind",
)
