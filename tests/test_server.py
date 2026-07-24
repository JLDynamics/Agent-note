import asyncio
import json

import pytest

from notes_mcp import embeddings, notes_store, server


@pytest.fixture
def notes_folder(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(notes_store, "get_notes_folder", lambda: folder)
    # server must never load the real model in tests
    monkeypatch.setattr(embeddings, "embed_text", lambda text: [1.0, 2.0, 3.0])
    return folder


def test_tool_surface_includes_conversation_import():
    assert set(server.TOOL_NAMES) == {
        "create_note", "import_conversation", "search", "list_recent",
        "list_tags", "read_note"
    }
    for removed in ("delete_note", "append_note", "show_note", "search_notes"):
        assert not hasattr(server, removed)


def test_create_note_description_tells_ai_to_infer_and_reuse_tags():
    """The model should infer normalized tags without asking the user."""
    import asyncio
    desc = asyncio.run(server.mcp.list_tools())
    cn = next(t for t in desc if t.name == "create_note").description
    assert "NEVER ask" in cn
    assert "3-8" in cn
    assert "list_tags" in cn
    assert "lowercase" in cn


def test_import_description_explains_raw_storage_and_create_note_path():
    tools = asyncio.run(server.mcp.list_tools())
    tool = next(t for t in tools if t.name == "import_conversation")
    assert "raw transcript is saved unchanged" in tool.description
    assert "create_note" in tool.description
    assert "connected agent" in tool.description
    assert "only preserves the raw transcript" in tool.description
    assert "sampling" not in tool.description.lower()


def test_create_note_saves_and_embeds(notes_folder):
    reply = json.loads(
        server.create_note(
            "hello world", tags=["User Context"], title="Greeting"
        )
    )
    assert "hello world" in notes_store.read_note(reply["path"])
    assert notes_store.note_info(reply["path"])["tags"] == ["user-context"]
    # fixture faked embed_text, so the companion file must exist
    assert embeddings.embedding_path(reply["path"]).exists()
    assert reply["warning"] is None
    assert reply["title"] == "Greeting"
    assert reply["tags"] == ["user-context"]
    assert reply["embedded"] is True


def test_create_note_rejects_empty_content(notes_folder):
    reply = json.loads(server.create_note("   "))
    assert "error" in reply
    assert "empty" in reply["error"]
    assert list(notes_folder.rglob("*.md")) == []


def test_create_note_invalid_tags_warns_but_saves(notes_folder):
    reply = json.loads(server.create_note("content", tags=["", None]))
    assert "invalid tags" in reply["warning"]
    assert "content" in notes_store.read_note(reply["path"])
    assert reply["embedded"] is True


def test_search_tool_returns_results(notes_folder):
    server.create_note("milk and eggs shopping")
    results = json.loads(server.search("milk"))
    assert isinstance(results, list) and results
    assert "milk" in results[0]["text"]


def test_list_recent_tool(notes_folder):
    server.create_note("fresh note")
    results = json.loads(server.list_recent(days=1))
    assert len(results) == 1


def test_list_tags_tool(notes_folder):
    server.create_note("one", tags=["MCP", "memory"])
    server.create_note("two", tags=["mcp", "python"])
    results = json.loads(server.list_tags())
    assert results[0] == {"tag": "mcp", "count": 2}


def test_read_note_tool_guards_paths(notes_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    reply = json.loads(server.read_note(str(secret)))
    assert "error" in reply
    assert "Refused" in reply["error"]


def test_read_note_tool_returns_json_content(notes_folder):
    created = json.loads(server.create_note("readable body", title="Read me"))
    reply = json.loads(server.read_note(created["path"]))
    assert reply["path"] == created["path"]
    assert "readable body" in reply["content"]
    assert "error" not in reply


def test_import_saves_raw_and_returns_agent_handoff(notes_folder):
    reply = json.loads(
        server.import_conversation(
            "User: remember this",
            original_date="2026-07-19",
            title="Memory chat",
        )
    )
    assert reply["status"] == "raw_saved"
    assert reply["agent_processing_required"] is True
    assert reply["conversation_id"] in reply["source_block_for_notes"]
    assert "Original conversation date: 2026-07-19" in reply["source_block_for_notes"]
    assert "create_note" in reply["next_action"]
    transcript = (
        notes_folder
        / ".raw"
        / "conversations"
        / reply["conversation_id"]
        / "conversation.txt"
    )
    assert transcript.read_text() == "User: remember this"


def test_agent_can_follow_import_handoff_with_create_note(notes_folder):
    reply = json.loads(
        server.import_conversation(
            "User: Keep the raw conversation unchanged.",
            original_date="2026-07-19",
        )
    )
    created = json.loads(
        server.create_note(
            "Raw conversation imports remain unchanged.\n\n"
            + reply["source_block_for_notes"],
            tags=["conversation-import", "raw-storage", "mcp"],
            title="Append-only conversation archive",
        )
    )
    note_path = created["path"]
    assert "Raw conversation imports remain unchanged" in notes_store.read_note(note_path)
    assert reply["conversation_id"] in notes_store.read_note(note_path)
    assert notes_store.note_info(note_path)["tags"] == [
        "conversation-import", "raw-storage", "mcp"
    ]
    assert embeddings.embedding_path(note_path).exists()
