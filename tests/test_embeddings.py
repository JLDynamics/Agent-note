import json
import math
from pathlib import Path

import pytest

from notes_mcp import embeddings, notes_store


@pytest.fixture
def notes_folder(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(notes_store, "get_notes_folder", lambda: folder)
    return folder


def fake_embed(text):
    """Deterministic 3-dim vector: food-ness, code-ness, length."""
    t = text.lower()
    return [float(t.count("milk") + t.count("food")),
            float(t.count("python") + t.count("code")),
            min(len(t) / 100.0, 1.0)]


def test_cosine_identical_and_orthogonal():
    assert math.isclose(embeddings.cosine([1.0, 0.0], [2.0, 0.0]), 1.0)
    assert math.isclose(embeddings.cosine([1.0, 0.0], [0.0, 5.0]), 0.0)
    assert embeddings.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0  # zero vector: no crash


def test_embedding_path():
    assert embeddings.embedding_path(Path("/x/2026-07-04/14-30-52.md")) == \
        Path("/x/2026-07-04/14-30-52.embedding")


def test_get_vector_creates_then_reuses(notes_folder):
    note, _ = notes_store.create_entry("milk milk milk")
    calls = []

    def counting_embed(text):
        calls.append(text)
        return fake_embed(text)

    v1 = embeddings.get_vector(note, counting_embed, model_name="fake-model")
    v2 = embeddings.get_vector(note, counting_embed, model_name="fake-model")
    assert v1 == v2
    assert len(calls) == 1  # second call hit the .embedding file
    saved = json.loads(embeddings.embedding_path(note).read_text())
    assert saved["model"] == "fake-model"


def test_get_vector_heals_corrupt_and_model_mismatch(notes_folder):
    note, _ = notes_store.create_entry("python code")
    emb = embeddings.embedding_path(note)

    emb.write_text("{ not json")
    v = embeddings.get_vector(note, fake_embed, model_name="fake-model")
    assert v == fake_embed(notes_store.note_info(note)["text"])

    emb.write_text(json.dumps({"model": "OTHER-model", "vector": [9.0, 9.0, 9.0]}))
    v = embeddings.get_vector(note, fake_embed, model_name="fake-model")
    assert v != [9.0, 9.0, 9.0]  # regenerated, not trusted


def test_get_vector_heals_wrong_shape_json(notes_folder):
    note, _ = notes_store.create_entry("python code")
    emb = embeddings.embedding_path(note)
    for bad in ["null", "[1, 2, 3]",
                '{"model": "fake-model", "vector": ["a", "b"]}',
                '{"model": "fake-model"}']:
        emb.write_text(bad)
        v = embeddings.get_vector(note, fake_embed, model_name="fake-model")
        assert v == fake_embed(notes_store.note_info(note)["text"])


def test_search_survives_bad_embedding_file(notes_folder):
    n1, _ = notes_store.create_entry("milk food")
    embeddings.embedding_path(n1).write_text("null")
    results = embeddings.search("milk", embed_fn=fake_embed,
                                model_name="fake-model")
    assert results and "milk" in results[0]["text"]


def test_try_embed_note_never_raises(notes_folder):
    note, _ = notes_store.create_entry("anything")

    def broken_embed(text):
        raise RuntimeError("model download failed")

    assert embeddings.try_embed_note(note, broken_embed) is False
    assert not embeddings.embedding_path(note).exists()
    assert note.exists()  # the note itself is untouched


def test_search_ranks_semantically(notes_folder):
    notes_store.create_entry("milk food milk food shopping")
    notes_store.create_entry("python code refactoring tips")
    results = embeddings.search("milk food", embed_fn=fake_embed,
                                model_name="fake-model")
    assert "milk" in results[0]["text"]
    assert results[0]["score"] >= results[-1]["score"]


def test_search_keyword_hit_inside_top_n_is_marked(notes_folder):
    notes_store.create_entry("OpenClaw gateway restart instructions")
    notes_store.create_entry("milk food")
    results = embeddings.search("OpenClaw", limit=2, embed_fn=fake_embed,
                                model_name="fake-model")
    hit = [r for r in results if "OpenClaw" in r["text"]]
    assert hit and hit[0]["match"] == "semantic+keyword"


def test_search_keyword_rescue_outside_top_n(notes_folder):
    # Distractors contain no keyword-signal words: fake_embed scores them
    # parallel to the query (cosine 1.0). The OpenClaw note is loaded with
    # "milk" words, pushing its vector away from the query so it falls
    # OUTSIDE the semantic top-2 — only the keyword rescue can return it.
    notes_store.create_entry("plain filler text about nothing")
    notes_store.create_entry("more plain filler words entirely")
    notes_store.create_entry("OpenClaw gateway milk food milk food milk")
    results = embeddings.search("OpenClaw", limit=2, embed_fn=fake_embed,
                                model_name="fake-model")
    rescued = [r for r in results if "OpenClaw" in r["text"]]
    assert rescued and rescued[0]["match"] == "keyword"
    assert len(results) == 3  # top-2 semantic + 1 rescued


def test_search_empty_folder_returns_empty(notes_folder):
    assert embeddings.search("anything", embed_fn=fake_embed,
                             model_name="fake-model") == []


def test_search_category_filter(notes_folder):
    notes_store.create_entry("feeling great about food", category="feelings")
    notes_store.create_entry("food inventory list", category="project_notes")
    results = embeddings.search("food", category="feelings",
                                embed_fn=fake_embed, model_name="fake-model")
    assert len(results) == 1
    assert results[0]["category"] == "feelings"


def test_search_long_note_snippet(notes_folder):
    notes_store.create_entry("food " + "x" * 2000)
    results = embeddings.search("food", embed_fn=fake_embed,
                                model_name="fake-model")
    assert results[0]["truncated"] is True
    assert len(results[0]["text"]) <= 310


def test_search_backfills_legacy_note(notes_folder):
    legacy = notes_folder / "2026-05-14-205701-groceries.md"
    legacy.write_text("# Groceries\n\nmilk food milk\n")
    results = embeddings.search("milk", embed_fn=fake_embed,
                                model_name="fake-model")
    assert any("milk" in r["text"] for r in results)
    assert embeddings.embedding_path(legacy).exists()  # backfilled
