"""Local embeddings: fastembed wrapper, companion files, cosine similarity."""
import json
import math
import re
from pathlib import Path

from notes_mcp import notes_store

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None  # lazy singleton — loading takes seconds, never do it at import

# One vector for an entire long note blurs unrelated topics together. Keep
# chunks small enough to represent one section while still carrying context.
CHUNK_TARGET_LENGTH = 1000


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


def chunk_text(text, target=CHUNK_TARGET_LENGTH):
    """Split text into contiguous, readable chunks with source offsets.

    Prefer paragraph, then sentence, then word boundaries. A single very long
    token still makes progress at the hard target. Joining the returned text
    always reconstructs the original input exactly.
    """
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        target_end = min(start + target, len(text))
        if target_end == len(text):
            end = len(text)
        else:
            minimum = min(start + max(1, target // 2), target_end)
            paragraph = text.rfind("\n\n", minimum, target_end)
            if paragraph != -1:
                end = paragraph + 2
            else:
                sentence_ends = [
                    match.end()
                    for match in re.finditer(
                        r"[.!?][)\]\"'\u201d]?\s+", text[minimum:target_end]
                    )
                ]
                if sentence_ends:
                    end = minimum + sentence_ends[-1]
                else:
                    whitespace = max(
                        text.rfind(" ", minimum, target_end),
                        text.rfind("\n", minimum, target_end),
                        text.rfind("\t", minimum, target_end),
                    )
                    end = whitespace + 1 if whitespace != -1 else target_end

        chunk = text[start:end]
        chunks.append({"start": start, "end": end, "text": chunk})
        start = end
    return chunks


def save_chunk_embeddings(note_path, chunks, model_name=MODEL_NAME):
    embedding_path(note_path).write_text(
        json.dumps({
            "model": model_name,
            "chunks": [
                {
                    "start": chunk["start"],
                    "end": chunk["end"],
                    "vector": chunk["vector"],
                }
                for chunk in chunks
            ],
        }),
        encoding="utf-8",
    )


def save_embedding(note_path, vector, model_name=MODEL_NAME):
    """Compatibility helper: save one vector spanning the complete note."""
    text = notes_store.note_info(note_path)["text"]
    save_chunk_embeddings(
        note_path,
        [{"start": 0, "end": len(text), "vector": vector}],
        model_name,
    )


def _valid_vector(vector):
    return isinstance(vector, list) and all(isinstance(x, (int, float)) for x in vector)


def _load_chunk_embeddings(note_path, model_name, text):
    try:
        data = json.loads(embedding_path(note_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("model") != model_name:
        return None
    chunks = data.get("chunks")
    # Upgrade the old one-vector format without re-embedding short notes. A
    # long note must be regenerated because its old vector blended all topics.
    if chunks is None and _valid_vector(data.get("vector")):
        text_chunks = chunk_text(text)
        if len(text_chunks) <= 1:
            upgraded = [{"start": 0, "end": len(text), "vector": data["vector"]}]
            save_chunk_embeddings(note_path, upgraded, model_name)
            return upgraded
    if not isinstance(chunks, list):
        return None
    if not all(
        isinstance(chunk, dict)
        and isinstance(chunk.get("start"), int)
        and isinstance(chunk.get("end"), int)
        and 0 <= chunk["start"] <= chunk["end"]
        and _valid_vector(chunk.get("vector"))
        for chunk in chunks
    ):
        return None
    return chunks


def get_chunk_vectors(note_path, embed_fn, model_name=MODEL_NAME, text=None):
    """Load chunk vectors or build them when missing/corrupt/legacy."""
    if text is None:
        text = notes_store.note_info(note_path)["text"]
    emb_file = embedding_path(note_path)
    if emb_file.exists():
        saved = _load_chunk_embeddings(note_path, model_name, text)
        if saved is not None:
            return saved

    chunks = chunk_text(text)
    embedded = [
        {
            "start": chunk["start"],
            "end": chunk["end"],
            "vector": embed_fn(chunk["text"]),
        }
        for chunk in chunks
    ]
    save_chunk_embeddings(note_path, embedded, model_name)
    return embedded


def get_vector(note_path, embed_fn, model_name=MODEL_NAME):
    """Compatibility helper returning the first chunk's vector."""
    chunks = get_chunk_vectors(note_path, embed_fn, model_name)
    return chunks[0]["vector"] if chunks else []


def try_embed_note(note_path, embed_fn=None):
    """Best-effort embed after a save. Never raises: a note must always
    save even when embedding fails (offline first run, etc.)."""
    try:
        get_chunk_vectors(note_path, embed_fn or embed_text)
        return True
    except Exception:
        return False


SNIPPET_LIMIT = notes_store.SNIPPET_LIMIT
SNIPPET_LENGTH = notes_store.SNIPPET_LENGTH


def _result(info, score, match, relevant_text=None):
    text = info["text"]
    truncated = len(text) > SNIPPET_LIMIT
    return {
        "path": info["path"],
        "date": info["date"],
        "title": info["title"],
        "category": info["category"],
        "score": round(score, 4),
        "match": match,
        "text": (relevant_text or text)[:SNIPPET_LENGTH] if truncated else text,
        "truncated": truncated,
    }


def _keyword_context(text, needles):
    """Return a window around the first exact query token in a long note."""
    lowered = text.lower()
    positions = [lowered.find(needle) for needle in needles]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return text
    start = max(0, min(positions) - SNIPPET_LENGTH // 3)
    return text[start:start + SNIPPET_LENGTH]


def search(query, limit=10, category=None, embed_fn=None, model_name=MODEL_NAME):
    """Hybrid search: semantic ranking + keyword rescue for exact tokens."""
    embed_fn = embed_fn or embed_text
    query_vector = embed_fn(query)
    # Tokenize so a multi-word query matches notes containing ALL terms in any
    # position/order — not just the verbatim phrase. Falls back to phrase
    # matching for single tokens and queries with no whitespace.
    needles = [t for t in query.lower().split() if t]
    if not needles:
        needles = [query.lower()]

    def has_keyword(text, title):
        hay = (text + " " + title).lower()
        # every token must appear somewhere in the note (phrase-substring was
        # too strict — "calgary costco" missed notes with both words apart)
        return all(n in hay for n in needles)

    scored = []
    for path in notes_store.iter_note_paths():
        info = notes_store.note_info(path)
        if category and info["category"] != category:
            continue
        chunk_vectors = get_chunk_vectors(
            path, embed_fn, model_name=model_name, text=info["text"]
        )
        chunk_scores = [
            (cosine(query_vector, chunk["vector"]), chunk)
            for chunk in chunk_vectors
        ]
        if chunk_scores:
            score, best_chunk = max(chunk_scores, key=lambda item: item[0])
            semantic_context = info["text"][best_chunk["start"]:best_chunk["end"]]
        else:
            score, semantic_context = 0.0, info["text"]
        keyword = has_keyword(info["text"], info["title"])
        relevant_text = (
            _keyword_context(info["text"], needles) if keyword else semantic_context
        )
        scored.append((score, keyword, info, relevant_text))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        _result(info, score, "semantic+keyword" if kw else "semantic", relevant)
        for score, kw, info, relevant in scored[:limit]
    ]
    # Keyword rescue, within the limit budget: exact-token hits that semantic
    # ranking buried are SWAPPED IN for the lowest-ranked non-keyword results,
    # so rare names the embedding model misses still surface — and the caller
    # never gets more than `limit` results.
    included = {r["path"] for r in results}
    rescue_candidates = [
        (score, info, relevant) for score, kw, info, relevant in scored[limit:]
        if kw and info["path"] not in included
    ]
    for ks, kinfo, krelevant in rescue_candidates:
        # replace the lowest-ranked pure-semantic result currently held
        for i in range(len(results) - 1, -1, -1):
            if results[i]["match"] == "semantic":
                results[i] = _result(kinfo, ks, "keyword", krelevant)
                break
        else:
            break  # nothing left to swap out
    return results
