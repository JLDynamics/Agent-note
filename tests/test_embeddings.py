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


def test_try_embed_note_never_raises(notes_folder):
    note, _ = notes_store.create_entry("anything")

    def broken_embed(text):
        raise RuntimeError("model download failed")

    assert embeddings.try_embed_note(note, broken_embed) is False
    assert not embeddings.embedding_path(note).exists()
    assert note.exists()  # the note itself is untouched
