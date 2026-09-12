"""Conversation pack persist tests. Uses tmp_path only."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.inventory import XLS_FORMULA_NOTICE
from src.core.packs import (
    NoWorkbookFilesError,
    attach_uploads_to_conversation,
    compose_attach_user_text,
    purge_orphan_pack_files,
    safe_filename,
)
from src.core.prompt import INVENTORY_PREAMBLE, NO_PACK_PREAMBLE, build_chat_prompt
from src.llm.runtime import RETRY_STEER_PREFIX
from src.ui.library import ConversationLibrary
from tests.workbook_fixtures import (
    write_books_xlsx,
    write_mixed_csv,
    write_rates_xlsx,
    write_tiny_xls,
)


def _library(tmp_path: Path) -> ConversationLibrary:
    return ConversationLibrary(tmp_path / "library.sqlite")


def test_compose_attach_user_text() -> None:
    assert compose_attach_user_text(["Rates.xlsx"]) == "Attached Rates.xlsx."
    assert compose_attach_user_text(
        ["Rates.xlsx", "Books.xlsx"], "What formulas link these files?"
    ) == (
        "Attached Rates.xlsx, Books.xlsx.\n\nWhat formulas link these files?"
    )


def test_attach_pack_copies_files_and_reuses_inventory(tmp_path: Path) -> None:
    library = _library(tmp_path)
    conversation = library.create_conversation()
    uploads_root = tmp_path / "uploads"
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    books = write_books_xlsx(tmp_path / "Books.xlsx")

    result = attach_uploads_to_conversation(
        library,
        conversation.id,
        [
            ("Rates.xlsx", rates.read_bytes()),
            ("folder/Books.xlsx", books.read_bytes()),
        ],
        uploads_root,
        question="Explain the link",
    )

    assert result.filenames == ["Rates.xlsx", "Books.xlsx"]
    assert "Explain the link" in result.user_text
    assert "Workbook inventory" in result.english_text
    assert "FORMULA" in result.prompt_text
    stored = library.get_conversation_pack(conversation.id)
    assert stored is not None
    assert stored.prompt_text == result.prompt_text
    files = library.list_pack_files(stored.id)
    assert {item.stored_relpath.split("/")[-1] for item in files} == {
        "Rates.xlsx",
        "Books.xlsx",
    }
    for item in files:
        assert (uploads_root / item.stored_relpath).is_file()


def test_replace_pack_orphans_previous_copy(tmp_path: Path) -> None:
    library = _library(tmp_path)
    conversation = library.create_conversation()
    uploads_root = tmp_path / "uploads"
    first = write_rates_xlsx(tmp_path / "Rates.xlsx")
    second = write_mixed_csv(tmp_path / "ledger.csv")

    first_result = attach_uploads_to_conversation(
        library,
        conversation.id,
        [("Rates.xlsx", first.read_bytes())],
        uploads_root,
    )
    first_rel = library.list_pack_files(first_result.pack.id)[0].stored_relpath
    assert (uploads_root / first_rel).is_file()

    second_result = attach_uploads_to_conversation(
        library,
        conversation.id,
        [("ledger.csv", second.read_bytes())],
        uploads_root,
    )
    assert second_result.replaced is True
    assert library.get_conversation_pack(conversation.id).id == second_result.pack.id
    assert library.get_pack(first_result.pack.id) is None
    assert not (uploads_root / first_rel).exists()


def test_one_pack_can_link_to_two_conversations(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.create_conversation("One")
    second = library.create_conversation("Two")
    pack = library.create_pack("Shared", "{}", "english", "prompt")
    library.replace_conversation_pack(first.id, pack.id)
    library.link_pack_to_conversation(second.id, pack.id)
    assert library.get_conversation_pack(first.id).id == pack.id
    assert library.get_conversation_pack(second.id).id == pack.id


def test_delete_conversation_purges_orphan_files(tmp_path: Path) -> None:
    library = _library(tmp_path)
    conversation = library.create_conversation()
    uploads_root = tmp_path / "uploads"
    rates = write_rates_xlsx(tmp_path / "Rates.xlsx")
    result = attach_uploads_to_conversation(
        library,
        conversation.id,
        [("Rates.xlsx", rates.read_bytes())],
        uploads_root,
    )
    rel = library.list_pack_files(result.pack.id)[0].stored_relpath
    library.delete_conversation(conversation.id)
    purged = purge_orphan_pack_files(library, uploads_root)
    assert rel in purged
    assert library.get_pack(result.pack.id) is None
    assert not (uploads_root / rel).exists()


def test_reject_upload_without_workbooks(tmp_path: Path) -> None:
    library = _library(tmp_path)
    conversation = library.create_conversation()
    with pytest.raises(NoWorkbookFilesError):
        attach_uploads_to_conversation(
            library,
            conversation.id,
            [("notes.txt", b"hello")],
            tmp_path / "uploads",
        )


def test_safe_filename_strips_paths() -> None:
    assert safe_filename(r"folder\Rates.xlsx") == "Rates.xlsx"
    assert safe_filename("../Books.csv") == "Books.csv"
    assert safe_filename(r"folder\wacccalc.xls") == "wacccalc.xls"


def test_attach_accepts_xls_and_keeps_xlsx_path(
    tmp_path: Path, monkeypatch
) -> None:
    library = _library(tmp_path)
    conversation = library.create_conversation()
    uploads_root = tmp_path / "uploads"
    xls = write_tiny_xls(tmp_path / "ledger.xls")
    monkeypatch.setattr(
        "src.core.inventory.convert_xls_to_temp_xlsx", lambda src: None
    )
    result = attach_uploads_to_conversation(
        library,
        conversation.id,
        [("ledger.xls", xls.read_bytes())],
        uploads_root,
    )
    assert result.filenames == ["ledger.xls"]
    assert "ledger.xls" in result.english_text
    assert XLS_FORMULA_NOTICE in result.english_text
    stored = library.list_pack_files(result.pack.id)
    assert stored[0].original_name == "ledger.xls"
    assert (uploads_root / stored[0].stored_relpath).is_file()


def test_build_chat_prompt_injects_inventory_or_warns() -> None:
    with_pack = build_chat_prompt("What formulas?", "PACK Rates.xlsx")
    assert INVENTORY_PREAMBLE in with_pack
    assert "Workbook inventory:" in with_pack
    assert "PACK Rates.xlsx" in with_pack
    assert "What formulas?" in with_pack
    assert "Do not invent numeric answers" in with_pack
    assert "Do not invent cell addresses" in with_pack
    assert "not in the inventory" in with_pack
    assert "Do not write Python" in with_pack

    bare = build_chat_prompt("Hello")
    assert NO_PACK_PREAMBLE in bare
    assert "Hello" in bare

    retry = build_chat_prompt("Hello", "PACK Rates.xlsx", retry=True)
    assert RETRY_STEER_PREFIX in retry
