"""Sidebar Recents list. Official Streamlit widgets only."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ui.chat_store import (
    CONVERSATION_ID_KEY,
    DELETE_CONFIRMED_ID_KEY,
    DELETE_DIALOG_OPEN_KEY,
    format_recent_button_label,
)
from ui.library import Conversation, ConversationLibrary


@dataclass(frozen=True)
class RecentsResult:
    """Sidebar Recents outcome for one script run."""

    opened_id: int | None = None
    deleted_id: int | None = None


def _close_delete_dialog() -> None:
    st.session_state[DELETE_DIALOG_OPEN_KEY] = False


@st.dialog("Delete conversation", on_dismiss=_close_delete_dialog)
def _confirm_delete_dialog(label: str, conversation_id: int) -> None:
    """Modal warning. Label matches the Recents button (title · date)."""
    st.write("You are about to permanently delete this conversation:")
    st.write(label)
    st.caption("This cannot be undone.")
    cancel, confirm = st.columns(2)
    if cancel.button("Cancel", use_container_width=True):
        _close_delete_dialog()
        st.rerun()
    if confirm.button("Delete", use_container_width=True):
        st.session_state[DELETE_CONFIRMED_ID_KEY] = conversation_id
        _close_delete_dialog()
        st.rerun()


def render_recents_sidebar(
    library: ConversationLibrary,
    *,
    disabled: bool,
) -> RecentsResult:
    """Draw Recents. Delete applies to the selected conversation."""
    st.subheader("Recents")
    conversations = library.list_conversations()
    if not conversations:
        st.caption("No saved conversations yet.")
        return RecentsResult()

    active = st.session_state.get(CONVERSATION_ID_KEY)
    opened_id: int | None = None
    active_conversation: Conversation | None = None
    for conversation in conversations:
        label = format_recent_button_label(
            conversation.title, conversation.updated_at
        )
        is_active = conversation.id == active
        if is_active:
            active_conversation = conversation
        if st.button(
            label,
            key=f"recent_{conversation.id}",
            use_container_width=True,
            disabled=disabled,
            type="primary" if is_active else "secondary",
        ):
            opened_id = conversation.id

    can_delete = active_conversation is not None and not disabled
    if st.button(
        "Delete conversation",
        use_container_width=True,
        disabled=not can_delete,
    ):
        st.session_state[DELETE_DIALOG_OPEN_KEY] = True

    if st.session_state.get(DELETE_DIALOG_OPEN_KEY) and active_conversation is not None:
        _confirm_delete_dialog(
            format_recent_button_label(
                active_conversation.title, active_conversation.updated_at
            ),
            active_conversation.id,
        )

    deleted_id = st.session_state.pop(DELETE_CONFIRMED_ID_KEY, None)
    if deleted_id is not None:
        deleted_id = int(deleted_id)

    return RecentsResult(opened_id=opened_id, deleted_id=deleted_id)
