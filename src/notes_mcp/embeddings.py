"""Local embeddings: fastembed wrapper, companion files, cosine similarity."""
import json
import math
from pathlib import Path

from notes_mcp import notes_store

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None  # lazy singleton — loading takes seconds, never do it at import


def embed_text(text):
    """Embed with the real model. Downloads ~90 MB on very first use."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=MODEL_NAME)
    return list(next(iter(_model.embed([text]))))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def embedding_path(note_path):
    return Path(note_path).with_suffix(".embedding")


def save_embedding(note_path, vector, model_name=MODEL_NAME):
    embedding_path(note_path).write_text(
        json.dumps({"model": model_name, "vector": vector}))


def get_vector(note_path, embed_fn, model_name=MODEL_NAME):
    """Load the note's vector; regenerate if missing, corrupt, or from
    another model (self-healing — also backfills legacy notes)."""
    emb_file = embedding_path(note_path)
    if emb_file.exists():
        try:
            data = json.loads(emb_file.read_text())
            if data.get("model") == model_name and isinstance(data.get("vector"), list):
                return data["vector"]
        except (json.JSONDecodeError, OSError):
            pass
    vector = embed_fn(notes_store.note_info(note_path)["text"])
    save_embedding(note_path, vector, model_name)
    return vector


def try_embed_note(note_path, embed_fn=None):
    """Best-effort embed after a save. Never raises: a note must always
    save even when embedding fails (offline first run, etc.)."""
    try:
        get_vector(note_path, embed_fn or embed_text)
        return True
    except Exception:
        return False


SNIPPET_LIMIT = 1500
SNIPPET_LENGTH = 300


def _result(info, score, match):
    text = info["text"]
    truncated = len(text) > SNIPPET_LIMIT
    return {
        "path": info["path"],
        "date": info["date"],
        "title": info["title"],
        "category": info["category"],
        "score": round(score, 4),
        "match": match,
        "text": text[:SNIPPET_LENGTH] if truncated else text,
        "truncated": truncated,
    }


def search(query, limit=10, category=None, embed_fn=None, model_name=MODEL_NAME):
    """Hybrid search: semantic ranking + keyword rescue for exact tokens."""
    embed_fn = embed_fn or embed_text
    query_vector = embed_fn(query)
    needle = query.lower()

    scored = []
    for path in notes_store.iter_note_paths():
        info = notes_store.note_info(path)
        if category and info["category"] != category:
            continue
        score = cosine(query_vector, get_vector(path, embed_fn, model_name))
        keyword = needle in info["text"].lower() or needle in info["title"].lower()
        scored.append((score, keyword, info))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        _result(info, score, "semantic+keyword" if kw else "semantic")
        for score, kw, info in scored[:limit]
    ]
    # keyword rescue: exact-token hits that semantic ranking left out
    included = {r["path"] for r in results}
    for score, kw, info in scored[limit:]:
        if kw and len(results) < limit + 3 and info["path"] not in included:
            results.append(_result(info, score, "keyword"))
    return results
