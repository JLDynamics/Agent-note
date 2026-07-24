import hashlib
import json
from datetime import datetime

import pytest

from notes_mcp import conversation_import, notes_store


@pytest.fixture
def notes_folder(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(notes_store, "get_notes_folder", lambda: folder)
    return folder


def test_raw_conversation_is_unchanged_and_metadata_is_separate(notes_folder):
    content = "User: first line\n\nAssistant: second line\n"
    record = conversation_import.save_raw_conversation(
        content,
        title="Planning chat",
        original_date="2026-06-14",
        now=datetime(2026, 7, 20, 9, 30, 0),
    )

    transcript = notes_folder / ".raw" / "conversations" / record["conversation_id"] / "conversation.txt"
    assert transcript.read_bytes() == content.encode("utf-8")
    metadata = json.loads((transcript.parent / "metadata.json").read_text())
    assert metadata["conversation_id"] == record["conversation_id"]
    assert metadata["original_date"] == "2026-06-14"
    assert metadata["title"] == "Planning chat"
    assert metadata["character_count"] == len(content)
    assert list(notes_store.iter_note_paths()) == []  # raw text is not a searchable note


def test_empty_conversation_is_refused_before_creating_raw_folder(notes_folder):
    with pytest.raises(ValueError, match="empty"):
        conversation_import.save_raw_conversation("  \n")
    assert not (notes_folder / ".raw").exists()


def test_metadata_checksum_matches_exact_raw_bytes(notes_folder):
    content = "User: Café ☕\nAssistant: Stored exactly.\n"
    record = conversation_import.save_raw_conversation(content)
    transcript = notes_folder / ".raw" / "conversations" / record["conversation_id"] / "conversation.txt"
    metadata = json.loads((transcript.parent / "metadata.json").read_text())

    assert metadata["sha256"] == hashlib.sha256(transcript.read_bytes()).hexdigest()
