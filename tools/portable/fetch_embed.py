"""Download the official Windows embeddable CPython zip into cache/."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

FALLBACK_VERSION = "3.13.7"


def embed_url(version: str) -> str:
    return (
        "https://www.python.org/ftp/python/"
        f"{version}/python-{version}-embed-amd64.zip"
    )


def fetch_embed_zip(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    versions = [
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        FALLBACK_VERSION,
    ]
    seen: set[str] = set()
    last_error = ""
    for version in versions:
        if version in seen:
            continue
        seen.add(version)
        dest = cache_dir / f"python-{version}-embed-amd64.zip"
        if dest.is_file() and dest.stat().st_size > 1_000_000:
            print(f"Using cached {dest.name}")
            return dest
        url = embed_url(version)
        print(f"Downloading {url}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:  # noqa: BLE001 — try the next official zip
            last_error = str(exc)
            if dest.exists():
                dest.unlink()
            continue
        if dest.is_file() and dest.stat().st_size > 1_000_000:
            return dest
        if dest.exists():
            dest.unlink()
    raise SystemExit(f"Could not download embeddable CPython. {last_error}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: fetch_embed.py <cache-dir>")
    path = fetch_embed_zip(Path(sys.argv[1]))
    print(path)


if __name__ == "__main__":
    main()
