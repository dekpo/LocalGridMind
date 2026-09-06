"""Local SQLite conversation library. No Streamlit import — safe for pytest."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

Role = Literal["user", "assistant"]

DEFAULT_TITLE = "New chat"
TITLE_MAX_CHARS = 48
ALLOWED_ROLES = frozenset({"user", "assistant"})

TITLE_PROMPT_PREFIX = (
    "Write a short title (maximum 6 words) for this analyst request. "
    "Reply with the title only. Do not use quotes. Do not invent numbers."
)


@dataclass(frozen=True)
class Conversation:
    """One saved thread in the Recents list."""

    id: int
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Message:
    """One persisted turn."""

    id: int
    conversation_id: int
    role: str
    content: str
    created_at: str
    elapsed_seconds: float | None = None

    def as_thread_item(self) -> dict[str, str | float]:
        item: dict[str, str | float] = {
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }
        if self.elapsed_seconds is not None:
            item["elapsed_seconds"] = self.elapsed_seconds
        return item


@dataclass(frozen=True)
class WorkbookPack:
    """Local copy + cached inventory. One pack may later join many chats."""

    id: int
    display_name: str
    inventory_json: str
    english_text: str
    prompt_text: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class WorkbookFile:
    """One stored workbook inside a pack."""

    id: int
    pack_id: int
    original_name: str
    stored_relpath: str
    size_bytes: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def heuristic_title(text: str, *, max_chars: int = TITLE_MAX_CHARS) -> str:
    """Safe Recents title from the first user line. Does not invent numbers."""
    stripped = text.strip()
    if not stripped:
        return DEFAULT_TITLE
    line = stripped.splitlines()[0].strip()
    collapsed = " ".join(line.split())
    if not collapsed:
        return DEFAULT_TITLE
    if len(collapsed) <= max_chars:
        return collapsed
    clipped = collapsed[:max_chars].rsplit(" ", 1)[0].rstrip()
    return clipped or collapsed[:max_chars]


def sanitize_model_title(text: str) -> str:
    """Turn a hidden completion into a short Recents title, or empty."""
    try:
        from llm.runtime import strip_reasoning_tags
    except ImportError:
        from src.llm.runtime import strip_reasoning_tags

    cleaned = strip_reasoning_tags(text)
    if not cleaned:
        return ""
    line = cleaned.splitlines()[0].strip().strip("\"'`")
    if not line:
        return ""
    return heuristic_title(line)


def build_title_prompt(user_text: str) -> str:
    return f"{TITLE_PROMPT_PREFIX}\n\n{user_text.strip()}"


class ConversationLibrary:
    """One-file SQLite store. Open and close a connection per call."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def create_conversation(self, title: str = DEFAULT_TITLE) -> Conversation:
        when = utc_now_iso()
        with self._session() as conn:
            cursor = conn.execute(
                """
                INSERT INTO conversations (title, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (title, when, when),
            )
            conversation_id = int(cursor.lastrowid)
        found = self.get_conversation(conversation_id)
        if found is None:
            raise RuntimeError("Failed to create conversation.")
        return found

    def list_conversations(self) -> list[Conversation]:
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        with self._session() as conn:
            row = conn.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return _conversation_from_row(row)

    def list_messages(self, conversation_id: int) -> list[Message]:
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT id, conversation_id, role, content, created_at,
                       elapsed_seconds
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [_message_from_row(row) for row in rows]

    def first_user_content(self, conversation_id: int) -> str:
        with self._session() as conn:
            row = conn.execute(
                """
                SELECT content FROM messages
                WHERE conversation_id = ? AND role = 'user'
                ORDER BY id ASC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            return ""
        return str(row["content"])

    def append_message(
        self,
        conversation_id: int,
        role: Role,
        content: str,
        *,
        created_at: str | None = None,
        elapsed_seconds: float | None = None,
    ) -> Message:
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Unsupported message role: {role}")
        if self.get_conversation(conversation_id) is None:
            raise KeyError(f"Unknown conversation: {conversation_id}")
        when = created_at if created_at else utc_now_iso()
        with self._session() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages (
                    conversation_id, role, content, created_at, elapsed_seconds
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, role, content, when, elapsed_seconds),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (when, conversation_id),
            )
            message_id = int(cursor.lastrowid)
        return Message(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=when,
            elapsed_seconds=elapsed_seconds,
        )

    def delete_conversation(self, conversation_id: int) -> None:
        with self._session() as conn:
            deleted = conn.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            if deleted.rowcount == 0:
                raise KeyError(f"Unknown conversation: {conversation_id}")

    def create_pack(
        self,
        display_name: str,
        inventory_json: str,
        english_text: str,
        prompt_text: str,
    ) -> WorkbookPack:
        when = utc_now_iso()
        with self._session() as conn:
            cursor = conn.execute(
                """
                INSERT INTO workbook_packs (
                    display_name, inventory_json, english_text, prompt_text,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (display_name, inventory_json, english_text, prompt_text, when, when),
            )
            pack_id = int(cursor.lastrowid)
        found = self.get_pack(pack_id)
        if found is None:
            raise RuntimeError("Failed to create workbook pack.")
        return found

    def get_pack(self, pack_id: int) -> WorkbookPack | None:
        with self._session() as conn:
            row = conn.execute(
                """
                SELECT id, display_name, inventory_json, english_text,
                       prompt_text, created_at, updated_at
                FROM workbook_packs
                WHERE id = ?
                """,
                (pack_id,),
            ).fetchone()
        if row is None:
            return None
        return _pack_from_row(row)

    def add_pack_file(
        self,
        pack_id: int,
        *,
        original_name: str,
        stored_relpath: str,
        size_bytes: int,
    ) -> WorkbookFile:
        if self.get_pack(pack_id) is None:
            raise KeyError(f"Unknown workbook pack: {pack_id}")
        with self._session() as conn:
            cursor = conn.execute(
                """
                INSERT INTO workbook_files (
                    pack_id, original_name, stored_relpath, size_bytes
                )
                VALUES (?, ?, ?, ?)
                """,
                (pack_id, original_name, stored_relpath, int(size_bytes)),
            )
            file_id = int(cursor.lastrowid)
        return WorkbookFile(
            id=file_id,
            pack_id=pack_id,
            original_name=original_name,
            stored_relpath=stored_relpath,
            size_bytes=int(size_bytes),
        )

    def list_pack_files(self, pack_id: int) -> list[WorkbookFile]:
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT id, pack_id, original_name, stored_relpath, size_bytes
                FROM workbook_files
                WHERE pack_id = ?
                ORDER BY id ASC
                """,
                (pack_id,),
            ).fetchall()
        return [_file_from_row(row) for row in rows]

    def replace_conversation_pack(
        self, conversation_id: int, pack_id: int
    ) -> None:
        if self.get_conversation(conversation_id) is None:
            raise KeyError(f"Unknown conversation: {conversation_id}")
        if self.get_pack(pack_id) is None:
            raise KeyError(f"Unknown workbook pack: {pack_id}")
        when = utc_now_iso()
        with self._session() as conn:
            conn.execute(
                "DELETE FROM conversation_packs WHERE conversation_id = ?",
                (conversation_id,),
            )
            conn.execute(
                """
                INSERT INTO conversation_packs (
                    conversation_id, pack_id, attached_at
                )
                VALUES (?, ?, ?)
                """,
                (conversation_id, pack_id, when),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (when, conversation_id),
            )

    def get_conversation_pack(self, conversation_id: int) -> WorkbookPack | None:
        with self._session() as conn:
            row = conn.execute(
                """
                SELECT p.id, p.display_name, p.inventory_json, p.english_text,
                       p.prompt_text, p.created_at, p.updated_at
                FROM conversation_packs AS cp
                JOIN workbook_packs AS p ON p.id = cp.pack_id
                WHERE cp.conversation_id = ?
                ORDER BY cp.attached_at DESC, p.id DESC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return _pack_from_row(row)

    def list_attached_pack_ids(self, conversation_id: int) -> list[int]:
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT pack_id FROM conversation_packs
                WHERE conversation_id = ?
                ORDER BY attached_at DESC, pack_id DESC
                """,
                (conversation_id,),
            ).fetchall()
        return [int(row["pack_id"]) for row in rows]

    def link_pack_to_conversation(
        self, conversation_id: int, pack_id: int
    ) -> None:
        """Add a pack link without dropping others (Phase 6b can use this)."""
        if self.get_conversation(conversation_id) is None:
            raise KeyError(f"Unknown conversation: {conversation_id}")
        if self.get_pack(pack_id) is None:
            raise KeyError(f"Unknown workbook pack: {pack_id}")
        when = utc_now_iso()
        with self._session() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversation_packs (
                    conversation_id, pack_id, attached_at
                )
                VALUES (?, ?, ?)
                """,
                (conversation_id, pack_id, when),
            )

    def delete_pack(self, pack_id: int) -> list[str]:
        """Remove a pack. Returns stored relative paths so callers can unlink."""
        relpaths = [item.stored_relpath for item in self.list_pack_files(pack_id)]
        with self._session() as conn:
            deleted = conn.execute(
                "DELETE FROM workbook_packs WHERE id = ?",
                (pack_id,),
            )
            if deleted.rowcount == 0:
                raise KeyError(f"Unknown workbook pack: {pack_id}")
        return relpaths

    def list_orphan_pack_ids(self) -> list[int]:
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT p.id FROM workbook_packs AS p
                LEFT JOIN conversation_packs AS cp ON cp.pack_id = p.id
                WHERE cp.pack_id IS NULL
                """
            ).fetchall()
        return [int(row["id"]) for row in rows]

    def purge_orphan_packs(self, keep_ids: set[int] | None = None) -> list[str]:
        """Delete packs with no conversation link. Return stored relpaths."""
        keep = keep_ids or set()
        relpaths: list[str] = []
        for pack_id in self.list_orphan_pack_ids():
            if pack_id in keep:
                continue
            relpaths.extend(self.delete_pack(pack_id))
        return relpaths

    def set_title(self, conversation_id: int, title: str) -> Conversation:
        cleaned = heuristic_title(title)
        when = utc_now_iso()
        with self._session() as conn:
            updated = conn.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                (cleaned, when, conversation_id),
            )
            if updated.rowcount == 0:
                raise KeyError(f"Unknown conversation: {conversation_id}")
        found = self.get_conversation(conversation_id)
        if found is None:
            raise KeyError(f"Unknown conversation: {conversation_id}")
        return found

    def needs_auto_title(self, conversation_id: int) -> bool:
        conversation = self.get_conversation(conversation_id)
        if conversation is None or conversation.title != DEFAULT_TITLE:
            return False
        roles = {item.role for item in self.list_messages(conversation_id)}
        return "user" in roles and "assistant" in roles

    def _init_schema(self) -> None:
        with self._session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    elapsed_seconds REAL,
                    FOREIGN KEY (conversation_id)
                        REFERENCES conversations(id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages (conversation_id, id);
                CREATE TABLE IF NOT EXISTS workbook_packs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    display_name TEXT NOT NULL,
                    inventory_json TEXT NOT NULL,
                    english_text TEXT NOT NULL,
                    prompt_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workbook_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pack_id INTEGER NOT NULL,
                    original_name TEXT NOT NULL,
                    stored_relpath TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    FOREIGN KEY (pack_id)
                        REFERENCES workbook_packs(id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS conversation_packs (
                    conversation_id INTEGER NOT NULL,
                    pack_id INTEGER NOT NULL,
                    attached_at TEXT NOT NULL,
                    PRIMARY KEY (conversation_id, pack_id),
                    FOREIGN KEY (conversation_id)
                        REFERENCES conversations(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (pack_id)
                        REFERENCES workbook_packs(id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_workbook_files_pack
                    ON workbook_files (pack_id);
                CREATE INDEX IF NOT EXISTS idx_conversation_packs_pack
                    ON conversation_packs (pack_id);
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "elapsed_seconds" not in columns:
                conn.execute(
                    "ALTER TABLE messages ADD COLUMN elapsed_seconds REAL"
                )

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _conversation_from_row(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=int(row["id"]),
        title=str(row["title"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _pack_from_row(row: sqlite3.Row) -> WorkbookPack:
    return WorkbookPack(
        id=int(row["id"]),
        display_name=str(row["display_name"]),
        inventory_json=str(row["inventory_json"]),
        english_text=str(row["english_text"]),
        prompt_text=str(row["prompt_text"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _file_from_row(row: sqlite3.Row) -> WorkbookFile:
    return WorkbookFile(
        id=int(row["id"]),
        pack_id=int(row["pack_id"]),
        original_name=str(row["original_name"]),
        stored_relpath=str(row["stored_relpath"]),
        size_bytes=int(row["size_bytes"]),
    )


def _message_from_row(row: sqlite3.Row) -> Message:
    raw_elapsed = row["elapsed_seconds"]
    elapsed = float(raw_elapsed) if raw_elapsed is not None else None
    return Message(
        id=int(row["id"]),
        conversation_id=int(row["conversation_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        created_at=str(row["created_at"]),
        elapsed_seconds=elapsed,
    )
