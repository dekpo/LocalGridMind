"""Copy uploads, persist a conversation pack, and drop orphaned files."""

from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .inventory import (
    ALLOWED_SUFFIXES,
    PackInventory,
    build_pack_inventory,
    is_workbook_name,
)

try:
    from ui.library import ConversationLibrary, WorkbookPack
except ImportError:  # pytest uses the repo root on sys.path
    from src.ui.library import ConversationLibrary, WorkbookPack

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class NoWorkbookFilesError(ValueError):
    """The upload contained no .xlsx / .xlsm / .xls / .csv files."""


@dataclass(frozen=True)
class AttachResult:
    pack: WorkbookPack
    inventory: PackInventory
    filenames: list[str]
    user_text: str
    english_text: str
    prompt_text: str
    replaced: bool


def compose_attach_user_text(filenames: Sequence[str], question: str = "") -> str:
    """English user turn for an attach, with an optional question underneath."""
    listed = ", ".join(filenames)
    prefix = f"Attached {listed}." if listed else "Attached workbooks."
    cleaned = question.strip()
    if cleaned:
        return f"{prefix}\n\n{cleaned}"
    return prefix


def uploads_from_files(files: Iterable[Any]) -> list[tuple[str, bytes]]:
    """Normalize Streamlit UploadedFile objects to (name, bytes)."""
    collected: list[tuple[str, bytes]] = []
    for item in files:
        name = str(getattr(item, "name", "") or "workbook")
        if hasattr(item, "getvalue"):
            data = item.getvalue()
        elif hasattr(item, "read"):
            data = item.read()
        else:
            continue
        if not isinstance(data, (bytes, bytearray)):
            data = bytes(data)
        collected.append((name, bytes(data)))
    return collected


def attach_uploads_to_conversation(
    library: ConversationLibrary,
    conversation_id: int,
    uploads: Sequence[tuple[str, bytes]],
    uploads_root: Path,
    *,
    question: str = "",
) -> AttachResult:
    """Copy allowed files, inventory once, attach to this Recents thread."""
    if library.get_conversation(conversation_id) is None:
        raise KeyError(f"Unknown conversation: {conversation_id}")

    previous_ids = library.list_attached_pack_ids(conversation_id)
    workbooks = [
        (name, data) for name, data in uploads if is_workbook_name(name)
    ]
    if not workbooks:
        raise NoWorkbookFilesError("No Excel or CSV files were found.")

    uploads_root = Path(uploads_root)
    uploads_root.mkdir(parents=True, exist_ok=True)
    pack_key = uuid.uuid4().hex
    pack_dir = uploads_root / pack_key
    pack_dir.mkdir(parents=True, exist_ok=True)

    saved: list[tuple[str, str, Path]] = []
    try:
        for original_name, data in workbooks:
            filename = unique_safe_filename(pack_dir, original_name)
            dest = pack_dir / filename
            dest.write_bytes(data)
            saved.append((original_name, f"{pack_key}/{filename}", dest))

        inventory = build_pack_inventory([path for _, _, path in saved])
        english = inventory.to_english()
        prompt = inventory.to_prompt()
        pack = library.create_pack(
            display_name=inventory.display_name(),
            inventory_json=inventory.to_json(),
            english_text=english,
            prompt_text=prompt,
        )
        for original_name, relpath, dest in saved:
            library.add_pack_file(
                pack.id,
                original_name=original_name,
                stored_relpath=relpath,
                size_bytes=dest.stat().st_size,
            )
        library.replace_conversation_pack(conversation_id, pack.id)
    except Exception:
        shutil.rmtree(pack_dir, ignore_errors=True)
        raise

    orphan_rels = library.purge_orphan_packs(keep_ids={pack.id})
    remove_stored_files(uploads_root, orphan_rels)

    filenames = [path.name for _, _, path in saved]
    return AttachResult(
        pack=pack,
        inventory=inventory,
        filenames=filenames,
        user_text=compose_attach_user_text(filenames, question),
        english_text=english,
        prompt_text=prompt,
        replaced=bool(previous_ids),
    )


def purge_orphan_pack_files(
    library: ConversationLibrary, uploads_root: Path
) -> list[str]:
    """Delete packs with no conversation and remove their local copies."""
    relpaths = library.purge_orphan_packs()
    remove_stored_files(Path(uploads_root), relpaths)
    return relpaths


def remove_stored_files(uploads_root: Path, relpaths: Sequence[str]) -> None:
    root = Path(uploads_root).resolve()
    parents: set[Path] = set()
    for relpath in relpaths:
        path = _safe_under_root(root, relpath)
        if path is None:
            continue
        if path.is_file():
            path.unlink()
        parents.add(path.parent)
    for parent in parents:
        if parent == root or not parent.is_dir():
            continue
        try:
            next(parent.iterdir())
        except StopIteration:
            parent.rmdir()


def unique_safe_filename(directory: Path, original_name: str) -> str:
    base = safe_filename(original_name)
    candidate = directory / base
    if not candidate.exists():
        return base
    stem = Path(base).stem
    suffix = Path(base).suffix
    index = 2
    while True:
        name = f"{stem}_{index}{suffix}"
        if not (directory / name).exists():
            return name
        index += 1


def safe_filename(original_name: str) -> str:
    name = Path(str(original_name).replace("\\", "/")).name
    cleaned = SAFE_NAME.sub("_", name).strip("._")
    suffix = Path(cleaned).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        stem = Path(cleaned).stem or "workbook"
        guessed = Path(str(original_name).replace("\\", "/")).suffix.lower()
        suffix = guessed if guessed in ALLOWED_SUFFIXES else ".xlsx"
        cleaned = f"{stem}{suffix}"
    if not cleaned:
        cleaned = "workbook.xlsx"
    return cleaned[:120]


def _safe_under_root(root: Path, relpath: str) -> Path | None:
    if not relpath or Path(relpath).is_absolute():
        return None
    candidate = (root / relpath.replace("\\", "/")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate
