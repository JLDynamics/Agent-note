import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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


def test_chunk_text_splits_long_text_without_losing_content():
    text = ("first section sentence. " * 80) + "\n\n" + ("second section " * 100)
    chunks = embeddings.chunk_text(text)
    assert len(chunks) >= 2
    assert "".join(chunk["text"] for chunk in chunks) == text
    assert chunks[0]["start"] == 0
    assert chunks[-1]["end"] == len(text)


def test_long_note_embeds_and_reuses_multiple_chunks(notes_folder):
    note, _ = notes_store.create_entry("alpha words " * 300)
    calls = []

    def counting_embed(text):
        calls.append(text)
        return fake_embed(text)

    first = embeddings.get_chunk_vectors(note, counting_embed, model_name="fake-model")
    first_call_count = len(calls)
    second = embeddings.get_chunk_vectors(note, counting_embed, model_name="fake-model")

    assert len(first) >= 3
    assert second == first
    assert first_call_count == len(first)
    assert len(calls) == first_call_count  # second load reused the companion file


def test_embedding_cache_regenerates_after_same_length_manual_edit(notes_folder):
    note, _ = notes_store.create_entry("milk")
    calls = []

    def counting_embed(text):
        calls.append(text)
        return fake_embed(text)

    first = embeddings.get_chunk_vectors(note, counting_embed, model_name="edit-model")
    original = note.read_text(encoding="utf-8")
    note.write_text(original.replace("milk", "code"), encoding="utf-8")
    second = embeddings.get_chunk_vectors(note, counting_embed, model_name="edit-model")

    assert len(calls) == 4  # meta + body, before and after the edit
    assert first != second
    saved = json.loads(embeddings.embedding_path(note).read_text())
    info = notes_store.note_info(note)
    assert saved["text_sha256"] == embeddings._text_fingerprint(
        embeddings.embed_source_text(info["title"], info["tags"], info["text"])
    )
    assert "meta_vector" in saved


def test_embedding_write_is_atomic_and_coerces_json_numbers(notes_folder):
    note, _ = notes_store.create_entry("content")

    class FloatLike:
        def __init__(self, value):
            self.value = value

        def __float__(self):
            return float(self.value)

    def save(index):
        embeddings.save_chunk_embeddings(
            note,
            [{"start": 0, "end": 8, "vector": [FloatLike(index), 2.0]}],
            model_name="atomic-model",
            text="content\n",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(save, range(20)))

    saved = json.loads(embeddings.embedding_path(note).read_text())
    assert saved["model"] == "atomic-model"
    assert isinstance(saved["chunks"][0]["vector"][0], float)
    assert not list(note.parent.glob(f".{note.stem}.embedding.*.tmp"))


def test_old_single_vector_short_note_rebuilds_with_title_meta(notes_folder):
    # Legacy one-vector files have no meta_vector. Notes with titles must
    # rebuild so title/tags participate in semantic search.
    note, _ = notes_store.create_entry("short note", title="Short title")
    embeddings.embedding_path(note).write_text(json.dumps({
        "model": "fake-model",
        "vector": [1.0, 2.0, 3.0],
    }))

    chunks = embeddings.get_chunk_vectors(note, fake_embed, model_name="fake-model")
    saved = json.loads(embeddings.embedding_path(note).read_text())
    body = notes_store.note_info(note)["text"]
    assert any(chunk.get("role") == "meta" for chunk in chunks)
    body_chunks = [chunk for chunk in chunks if chunk.get("role") != "meta"]
    assert body_chunks == [{
        "start": 0,
        "end": len(body),
        "vector": fake_embed(body),
    }]
    assert saved["chunks"] == body_chunks
    assert saved["meta_vector"] == fake_embed("Short title")


def test_get_vector_creates_then_reuses(notes_folder):
    note, _ = notes_store.create_entry("milk milk milk")
    calls = []

    def counting_embed(text):
        calls.append(text)
        return fake_embed(text)

    v1 = embeddings.get_vector(note, counting_embed, model_name="fake-model")
    v2 = embeddings.get_vector(note, counting_embed, model_name="fake-model")
    assert v1 == v2
    # meta (title) + body on first build; second load reuses the companion file
    assert len(calls) == 2
    saved = json.loads(embeddings.embedding_path(note).read_text())
    assert saved["model"] == "fake-model"
    assert "meta_vector" in saved


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
    # Distractors align with the query vector; the OpenClaw note (title + body)
    # is forced orthogonal so it falls outside the semantic top-2. Only keyword
    # rescue can surface it, swapping into a pure-semantic slot within `limit`.
    notes_store.create_entry("plain filler text about nothing", title="Filler A")
    notes_store.create_entry("more plain filler words entirely", title="Filler B")
    notes_store.create_entry(
        "OpenClaw gateway restart steps", title="OpenClaw ops"
    )

    def rescue_embed(text):
        lowered = text.lower().strip()
        if lowered == "openclaw":
            return [1.0, 0.0, 0.0]
        if "openclaw" in lowered:
            return [0.0, 1.0, 0.0]
        return [1.0, 0.0, 0.0]

    results = embeddings.search(
        "OpenClaw", limit=2, embed_fn=rescue_embed, model_name="rescue-model"
    )
    rescued = [r for r in results if "OpenClaw" in r["text"]]
    assert rescued and rescued[0]["match"] == "keyword"
    assert len(results) == 2  # limit is a hard cap: swap-in, never exceed


def test_search_empty_folder_returns_empty(notes_folder):
    assert embeddings.search("anything", embed_fn=fake_embed,
                             model_name="fake-model") == []


def test_search_blank_query_and_nonpositive_limit_do_no_embedding_work(notes_folder):
    notes_store.create_entry("content")

    def should_not_run(text):
        raise AssertionError("invalid searches should stop before embedding")

    assert embeddings.search("   ", embed_fn=should_not_run) == []
    assert embeddings.search("content", limit=0, embed_fn=should_not_run) == []
    assert embeddings.search("content", limit=-1, embed_fn=should_not_run) == []


def test_search_keyword_matches_all_tokens_anywhere(notes_folder):
    # Multi-token query: every token must appear somewhere in the note, in any
    # order/position — not the verbatim phrase. Phrase-substring matching was
    # the old behavior and missed notes with the words in separate sentences.
    notes_store.create_entry("calgary in the morning; later I went to costco")
    notes_store.create_entry("totally unrelated note about python")
    results = embeddings.search("calgary costco", embed_fn=fake_embed,
                                model_name="fake-model")
    hits = [r for r in results if "calgary" in r["text"]]
    assert hits, "both tokens present in the same note should keyword-match"


def test_search_keyword_token_absent_excludes_note(notes_folder):
    # If any token is missing, it is not a keyword match (don't over-recall).
    notes_store.create_entry("calgary only, no other query word here")
    results = embeddings.search("calgary costco", embed_fn=fake_embed,
                                model_name="fake-model")
    assert all("costco" not in r["text"] for r in results)
    # still may return semantically, but never as a keyword match
    assert all(r["match"] == "semantic" for r in results)


def test_search_respects_limit_budget(notes_folder):
    # limit is a hard cap: keyword rescue swaps hits in for the lowest
    # pure-semantic results, never appends past the limit.
    for i in range(8):
        notes_store.create_entry(f"plain filler number {i} about nothing")
    notes_store.create_entry("OpenClaw gateway milk food milk food milk")
    results = embeddings.search("OpenClaw", limit=3, embed_fn=fake_embed,
                                model_name="fake-model")
    assert len(results) <= 3
    assert any("OpenClaw" in r["text"] for r in results)


def test_search_tag_filter(notes_folder):
    notes_store.create_entry(
        "feeling great about food", tags=["feelings", "personal"]
    )
    notes_store.create_entry("food inventory list", tags=["project", "inventory"])
    results = embeddings.search(
        "food", tags=["Feelings"], embed_fn=fake_embed, model_name="fake-model"
    )
    assert len(results) == 1
    assert results[0]["tags"] == ["feelings", "personal"]


def test_tag_match_boosts_relevant_note_and_reports_signal(notes_folder):
    notes_store.create_entry(
        "plain words that embeddings rank weakly",
        tags=["conversation-import", "memory"],
    )
    notes_store.create_entry("plain unrelated words", tags=["gardening"])

    def flat_embed(text):
        return [1.0, 0.0, 0.0]

    results = embeddings.search(
        "How does conversation import work?",
        embed_fn=flat_embed,
        model_name="flat-model",
    )
    assert results[0]["tags"] == ["conversation-import", "memory"]
    assert "tag" in results[0]["match"]
    assert results[0]["matched_tags"] == ["conversation-import"]


def test_newest_note_wins_when_relevance_is_close(notes_folder):
    notes_store.create_entry(
        "The earlier storage plan used SQLite.",
        tags=["storage-direction"],
        now=datetime(2026, 6, 1, 9, 0, 0),
    )
    notes_store.create_entry(
        "The current storage plan uses Markdown notes and tags.",
        tags=["storage-direction"],
        now=datetime(2026, 7, 21, 9, 0, 0),
    )

    def close_topic_embed(text):
        lowered = text.lower()
        if lowered == "storage direction":
            similarity = 1.0
        elif "sqlite" in lowered:
            similarity = 0.96
        else:
            similarity = 0.94
        return [similarity, math.sqrt(max(0.0, 1 - similarity**2))]

    results = embeddings.search(
        "storage direction",
        embed_fn=close_topic_embed,
        model_name="close-topic-model",
    )
    assert "current storage plan" in results[0]["text"]
    assert "earlier storage plan" in results[1]["text"]
    assert results[0]["score"] < results[1]["score"]


def test_newer_unrelated_note_does_not_beat_relevant_older_note(notes_folder):
    notes_store.create_entry(
        "The established memory storage design uses Markdown.",
        now=datetime(2026, 6, 1, 9, 0, 0),
    )
    notes_store.create_entry(
        "New gardening plans for tomatoes.",
        now=datetime(2026, 7, 21, 9, 0, 0),
    )

    def separated_topic_embed(text):
        lowered = text.lower()
        if lowered == "memory storage" or "markdown" in lowered:
            return [1.0, 0.0]
        return [0.0, 1.0]

    results = embeddings.search(
        "memory storage",
        embed_fn=separated_topic_embed,
        model_name="separated-topic-model",
    )
    assert "Markdown" in results[0]["text"]


def test_search_long_note_snippet(notes_folder):
    notes_store.create_entry("food " + "x" * 2000)
    results = embeddings.search("food", embed_fn=fake_embed,
                                model_name="fake-model")
    assert results[0]["truncated"] is True
    assert len(results[0]["text"]) <= 310


def test_search_long_note_returns_the_relevant_semantic_chunk(notes_folder):
    notes_store.create_entry(
        ("milk groceries shopping " * 100)
        + "\n\n"
        + ("python code refactoring details " * 80)
    )

    def topic_embed(text):
        lowered = text.lower()
        return [
            float("software" in lowered or "python" in lowered),
            float("milk" in lowered),
            0.1,
        ]

    results = embeddings.search(
        "software", limit=1, embed_fn=topic_embed, model_name="topic-model"
    )
    assert results[0]["match"] == "semantic"
    assert "python" in results[0]["text"]
    assert "milk" not in results[0]["text"]


def test_search_backfills_legacy_note(notes_folder):
    legacy = notes_folder / "2026-05-14-205701-groceries.md"
    legacy.write_text("# Groceries\n\nmilk food milk\n")
    results = embeddings.search("milk", embed_fn=fake_embed,
                                model_name="fake-model")
    assert any("milk" in r["text"] for r in results)
    assert embeddings.embedding_path(legacy).exists()  # backfilled


def test_search_skips_unreadable_notes(notes_folder):
    notes_store.create_entry("milk food shopping list")
    bad = notes_folder / "2026-07-04" / "00-00-00.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"\xff\xfe")
    results = embeddings.search("milk", embed_fn=fake_embed, model_name="fake-model")
    assert results and "milk" in results[0]["text"]


def test_search_drops_weak_semantic_hits(notes_folder):
    notes_store.create_entry(
        "Completely unrelated gardening notes about roses.",
        title="Garden",
    )
    notes_store.create_entry(
        "milk food milk food shopping",
        title="Groceries",
    )

    def separated(text):
        lowered = text.lower()
        if "milk" in lowered or lowered == "milk":
            return [1.0, 0.0]
        return [0.0, 1.0]

    results = embeddings.search(
        "milk", embed_fn=separated, model_name="floor-model"
    )
    assert len(results) == 1
    assert "milk" in results[0]["text"]


def test_search_keeps_weak_semantic_when_keyword_hits(notes_folder):
    notes_store.create_entry(
        "The OpenClaw gateway restart checklist lives here.",
        title="Ops",
    )

    def orthogonal(text):
        return [0.0, 1.0]

    results = embeddings.search(
        "OpenClaw", embed_fn=orthogonal, model_name="keyword-floor-model"
    )
    assert results and "OpenClaw" in results[0]["text"]
    assert "keyword" in results[0]["match"]


def test_title_influences_semantic_ranking(notes_folder):
    notes_store.create_entry(
        "details about the mechanism and wiring",
        title="Conversation import design",
        tags=["mcp"],
    )
    notes_store.create_entry(
        "details about the mechanism and wiring",
        title="Tomato trellis design",
        tags=["garden"],
    )

    def topic_embed(text):
        lowered = text.lower()
        if "conversation import" in lowered:
            return [1.0, 0.0, 0.0]
        if "tomato" in lowered or "garden" in lowered:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    results = embeddings.search(
        "conversation import",
        embed_fn=topic_embed,
        model_name="title-model",
    )
    assert results[0]["title"] == "Conversation import design"
