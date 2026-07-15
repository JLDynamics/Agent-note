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


def test_tool_surface_is_exactly_four():
    assert set(server.TOOL_NAMES) == {"create_note", "search", "list_recent", "read_note"}
    for removed in ("delete_note", "append_note", "show_note", "search_notes"):
        assert not hasattr(server, removed)


def test_create_note_description_tells_ai_to_infer():
    """The description the AI sees must say to infer category/title itself,
    never ask the user — that's what stops the back-and-forth."""
    import asyncio
    desc = asyncio.run(server.mcp.list_tools())
    cn = next(t for t in desc if t.name == "create_note").description
    assert "NEVER ask" in cn
    for label in notes_store.CATEGORIES:
        assert label in cn, f"category {label!r} missing from description"


def test_category_help_matches_categories():
    """_CATEGORY_HELP must list exactly notes_store.CATEGORIES — keep the
    tool description and the validation set in sync."""
    assert set(server._CATEGORY_HELP) == set(notes_store.CATEGORIES)


def test_create_note_saves_and_embeds(notes_folder):
    reply = json.loads(server.create_note("hello world", category="user_context"))
    assert "hello world" in notes_store.read_note(reply["path"])
    # fixture faked embed_text, so the companion file must exist
    assert embeddings.embedding_path(reply["path"]).exists()
    assert reply["warning"] is None


def test_create_note_invalid_category_warns_but_saves(notes_folder):
    reply = json.loads(server.create_note("content", category="bogus"))
    assert "bogus" in reply["warning"]
    assert "content" in notes_store.read_note(reply["path"])


def test_search_tool_returns_results(notes_folder):
    server.create_note("milk and eggs shopping")
    results = json.loads(server.search("milk"))
    assert isinstance(results, list) and results
    assert "milk" in results[0]["text"]


def test_list_recent_tool(notes_folder):
    server.create_note("fresh note")
    results = json.loads(server.list_recent(days=1))
    assert len(results) == 1


def test_read_note_tool_guards_paths(notes_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    reply = server.read_note(str(secret))
    assert "Refused" in reply
