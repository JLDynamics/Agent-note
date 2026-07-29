import pytest

from agent_note import embeddings, notes_store, service


@pytest.fixture
def notes_folder(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(notes_store, "get_notes_folder", lambda: folder)
    monkeypatch.setattr(embeddings, "embed_text", lambda text: [1.0, 2.0, 3.0])
    return folder


def test_create_service_owns_storage_embedding_and_result(notes_folder):
    result = service.create_note(
        "Complete durable context",
        tags=["Memory System"],
        title="Durable context",
        summary="The note preserves complete durable context.",
    )

    assert result == {
        "path": result["path"],
        "title": "Durable context",
        "tags": ["memory-system"],
        "summary": "The note preserves complete durable context.",
        "embedded": True,
        "warning": None,
    }
    assert "Complete durable context" in notes_store.read_note(result["path"])
    assert notes_store.note_info(result["path"])["summary"] == result["summary"]
    assert embeddings.embedding_path(result["path"]).exists()


def test_create_service_preserves_note_when_embedding_fails(notes_folder, monkeypatch):
    monkeypatch.setattr(embeddings, "try_embed_note", lambda path: False)
    result = service.create_note("Saved before embedding")

    assert result["embedded"] is False
    assert "Saved before embedding" in notes_store.read_note(result["path"])


def test_import_service_preserves_raw_and_returns_broad_first_handoff(notes_folder):
    result = service.import_conversation(
        "User: preserve this complete conversation\r\n",
        original_date="2026-07-25",
        title="Import",
    )

    assert result["status"] == "raw_saved"
    assert result["agent_processing_required"] is True
    assert "broad session handoff" in result["next_action"]
    assert result["next_action"].index("broad session handoff") < result[
        "next_action"
    ].index("search for related notes")
    assert "a few useful tags (up to eight) that help retrieval" in result[
        "next_action"
    ]
    assert "3-8 useful tags" not in result["next_action"]
    assert result["source_block_for_notes"] == (
        "Original conversation date: 2026-07-25\n"
        f"Source conversation: {result['conversation_id']}"
    )
    assert notes_folder.joinpath(
        ".raw",
        "conversations",
        result["conversation_id"],
        "conversation.txt",
    ).read_bytes() == b"User: preserve this complete conversation\r\n"


def test_create_service_reports_validation_error_without_writing(notes_folder):
    result = service.create_note(" \n", title="Empty")

    assert result == {"error": "note content cannot be empty"}
    assert list(notes_folder.rglob("*.md")) == []
