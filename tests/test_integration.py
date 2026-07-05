"""Real-model test. Downloads ~90 MB on first run. Excluded by default:
run with `uv run pytest -m slow`."""
import pytest

from notes_mcp import embeddings, notes_store


@pytest.mark.slow
def test_real_semantic_search(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(notes_store, "get_notes_folder", lambda: folder)

    notes_store.create_entry("meal prep plan to cut food spending")
    notes_store.create_entry("refactoring the python test suite")

    results = embeddings.search("saving money on groceries", limit=1)
    assert "meal prep" in results[0]["text"]  # semantic match, zero shared words
