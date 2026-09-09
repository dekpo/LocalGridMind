"""Enable site-packages on an official Windows embeddable CPython folder."""

from __future__ import annotations

import sys
from pathlib import Path


def enable_embed_site(runtime: Path) -> None:
    pths = sorted(runtime.glob("python*._pth"))
    if not pths:
        raise SystemExit(f"No python*._pth in {runtime}")
    pth = pths[0]
    lines: list[str] = []
    saw_site = False
    saw_packages = False
    for raw in pth.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.lstrip("#").strip() == "import site":
            if not saw_site:
                lines.append("import site")
                saw_site = True
            continue
        if "site-packages" in stripped:
            saw_packages = True
        lines.append(raw)
    if not saw_packages:
        insert_at = len(lines)
        if lines and lines[-1].strip() == "import site":
            insert_at = len(lines) - 1
        lines.insert(insert_at, "Lib/site-packages")
    if not saw_site:
        lines.append("import site")
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (runtime / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: enable_embed_site.py <runtime-folder>")
    enable_embed_site(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
