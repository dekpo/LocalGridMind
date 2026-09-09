"""Thin exe: start the official embeddable Python, which runs Streamlit.

PyInstaller must not import llama_cpp or Streamlit in this process.
Smart App Control blocks those DLLs when an unsigned frozen exe loads
them (Bad Image 0xc0e90002). The signed python.org runtime can load them.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def portable_root() -> Path:
    """Folder that holds the exe (frozen) or the Git repo (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def streamlit_command(root: Path) -> list[str]:
    """Command that runs Streamlit with the portable CPython, not this exe."""
    python = root / "runtime" / "python.exe"
    app_path = root / "src" / "app.py"
    return [
        str(python),
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
        "--server.headless=false",
    ]


def main() -> None:
    root = portable_root()
    os.chdir(root)
    python = root / "runtime" / "python.exe"
    app_path = root / "src" / "app.py"
    if not python.is_file():
        sys.stderr.write(f"Cannot find the portable Python: {python}\n")
        sys.exit(1)
    if not app_path.is_file():
        sys.stderr.write(f"Cannot find the app script: {app_path}\n")
        sys.exit(1)
    raise SystemExit(subprocess.call(streamlit_command(root)))


if __name__ == "__main__":
    main()
