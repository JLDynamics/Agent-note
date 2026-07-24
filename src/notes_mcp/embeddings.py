"""Local embeddings: fastembed wrapper, companion files, cosine similarity."""
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
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
    # FastEmbed returns NumPy float32 values, which the standard JSON encoder
    # cannot serialize. Convert once at the boundary so every stored vector is
    # plain portable JSON numbers.
    return [float(value) for value in next(iter(_model.embed([text])))]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def embedding_path(note_path):
    return Path(note_path).with_suffix(".embedding")


def embed_source_text(title, tags, body):
    """Text used for vectors and cache fingerprints: title + tags + body.

    Title and tags are the strongest topic signals on a note; body-only
    embeddings miss them. Body chunk offsets stay relative to the body alone.
    """
    parts = []
    title = (title or "").strip()
    if title:
        parts.append(title)
    if tags:
        parts.append(" ".join(tags))
    header = "\n".join(parts)
    body = body or ""
    if header and body:
        return f"{header}\n\n{body}"
    return header or body


def _meta_text(title, tags):
    parts = []
    title = (title or "").strip()
    if title:
        parts.append(title)
    if tags:
        parts.append(" ".join(tags))
    return "\n".join(parts)


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


def _text_fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write_json(path, payload):
    """Replace one JSON file atomically, even with simultaneous searches."""
    path = Path(path)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def save_chunk_embeddings(
    note_path,
    chunks,
    model_name=MODEL_NAME,
    text=None,
    meta_vector=None,
):
    if text is None:
        info = notes_store.note_info(note_path)
        text = embed_source_text(info["title"], info["tags"], info["text"])
    payload = {
        "model": model_name,
        "text_sha256": _text_fingerprint(text),
        "chunks": [
            {
                "start": chunk["start"],
                "end": chunk["end"],
                "vector": [float(value) for value in chunk["vector"]],
            }
            for chunk in chunks
            if chunk.get("role") != "meta"
        ],
    }
    if meta_vector is None:
        for chunk in chunks:
            if chunk.get("role") == "meta":
                meta_vector = chunk["vector"]
                break
    if meta_vector is not None:
        payload["meta_vector"] = [float(value) for value in meta_vector]
    _atomic_write_json(embedding_path(note_path), payload)


def save_embedding(note_path, vector, model_name=MODEL_NAME):
    """Compatibility helper: save one vector spanning the complete note body."""
    info = notes_store.note_info(note_path)
    body = info["text"]
    source = embed_source_text(info["title"], info["tags"], body)
    save_chunk_embeddings(
        note_path,
        [{"start": 0, "end": len(body), "vector": vector}],
        model_name,
        text=source,
    )


def _valid_vector(vector):
    return isinstance(vector, list) and all(isinstance(x, (int, float)) for x in vector)


def _cache_is_current_enough_for_upgrade(note_path):
    """Legacy caches can be reused only when the note was not edited later."""
    try:
        return (
            embedding_path(note_path).stat().st_mtime
            >= Path(note_path).stat().st_mtime
        )
    except OSError:
        return False


def _body_chunks(chunks):
    return [chunk for chunk in chunks if chunk.get("role") != "meta"]


def _chunks_cover_text(chunks, text):
    body = _body_chunks(chunks)
    if not body:
        return text == ""
    if body[0]["start"] != 0 or body[-1]["end"] != len(text):
        return False
    return all(
        current["end"] == following["start"]
        for current, following in zip(body, body[1:])
    )


def _load_chunk_embeddings(note_path, model_name, body, source, meta_expected):
    try:
        data = json.loads(embedding_path(note_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("model") != model_name:
        return None
    stored_fingerprint = data.get("text_sha256")
    if stored_fingerprint is not None and stored_fingerprint != _text_fingerprint(source):
        return None
    legacy_cache = stored_fingerprint is None
    if legacy_cache and not _cache_is_current_enough_for_upgrade(note_path):
        return None
    chunks = data.get("chunks")
    meta_vector = data.get("meta_vector")
    if meta_vector is not None and not _valid_vector(meta_vector):
        return None
    # Upgrade the old one-vector format without re-embedding short notes. A
    # long note must be regenerated because its old vector blended all topics.
    # Only reuse when title/tags do not require a separate meta vector (or one
    # is already stored); otherwise fall through and rebuild fully.
    if chunks is None and _valid_vector(data.get("vector")):
        text_chunks = chunk_text(body)
        if len(text_chunks) <= 1 and not (meta_expected and meta_vector is None):
            upgraded = [{"start": 0, "end": len(body), "vector": data["vector"]}]
            if meta_vector is not None:
                upgraded.insert(
                    0, {"role": "meta", "start": 0, "end": 0, "vector": meta_vector}
                )
            save_chunk_embeddings(
                note_path, upgraded, model_name, text=source, meta_vector=meta_vector
            )
            return upgraded
        return None
    # Body-only caches predate title/tag signals — rebuild when meta is needed.
    # Fingerprint-less legacy caches also rebuild once so hashes get stored.
    if legacy_cache or (meta_expected and meta_vector is None):
        return None
    if not isinstance(chunks, list):
        return None
    if not all(
        isinstance(chunk, dict)
        and isinstance(chunk.get("start"), int)
        and isinstance(chunk.get("end"), int)
        and 0 <= chunk["start"] <= chunk["end"]
        and chunk["end"] <= len(body)
        and _valid_vector(chunk.get("vector"))
        for chunk in chunks
    ):
        return None
    if not _chunks_cover_text(chunks, body):
        return None
    loaded = list(chunks)
    if meta_vector is not None:
        loaded.insert(0, {"role": "meta", "start": 0, "end": 0, "vector": meta_vector})
    return loaded


def get_chunk_vectors(note_path, embed_fn, model_name=MODEL_NAME, text=None, info=None):
    """Load chunk vectors or build them when missing/corrupt/legacy.

    Body chunks keep offsets into the note body for snippets. A separate meta
    chunk embeds title + tags so topic labels influence semantic ranking.
    """
    if info is None:
        info = notes_store.note_info(note_path)
    body = info["text"] if text is None else text
    title = info["title"]
    tags = info["tags"]
    source = embed_source_text(title, tags, body)
    meta = _meta_text(title, tags)
    emb_file = embedding_path(note_path)
    if emb_file.exists():
        saved = _load_chunk_embeddings(
            note_path, model_name, body, source, meta_expected=bool(meta)
        )
        if saved is not None:
            return saved

    embedded = []
    meta_vector = None
    if meta:
        meta_vector = embed_fn(meta)
        embedded.append(
            {"role": "meta", "start": 0, "end": 0, "vector": meta_vector}
        )
    for chunk in chunk_text(body):
        embedded.append(
            {
                "start": chunk["start"],
                "end": chunk["end"],
                "vector": embed_fn(chunk["text"]),
            }
        )
    save_chunk_embeddings(
        note_path, embedded, model_name, text=source, meta_vector=meta_vector
    )
    return embedded


def get_vector(note_path, embed_fn, model_name=MODEL_NAME):
    """Compatibility helper returning the first body chunk's vector."""
    chunks = _body_chunks(get_chunk_vectors(note_path, embed_fn, model_name))
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
TAG_MATCH_BOOST = 0.12
# Pure semantic hits below this floor are noise for agents; keyword/tag hits
# always pass so rare exact names still surface via rescue.
MIN_SEMANTIC_SCORE = 0.2
# Notes inside this score distance are close enough that recency is a safer
# authority signal than tiny embedding-score differences. Larger relevance
# gaps always win, preventing unrelated recent notes from taking over.
RECENCY_RELEVANCE_BAND = 0.05


@dataclass
class _ScoredNote:
    rank_score: float
    semantic_score: float
    keyword: bool
    matched_tags: list[str]
    info: dict
    relevant_text: str


def _result(
    info,
    semantic_score,
    rank_score,
    match,
    relevant_text=None,
    matched_tags=None,
):
    text = info["text"]
    truncated = len(text) > SNIPPET_LIMIT
    return {
        "path": info["path"],
        "date": info["date"],
        "title": info["title"],
        "tags": info["tags"],
        "score": round(rank_score, 4),
        "semantic_score": round(semantic_score, 4),
        "match": match,
        "matched_tags": matched_tags or [],
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


def _matching_tags(query, tags):
    normalized_query = notes_store.normalize_tag(query)
    if not normalized_query:
        return []
    query_parts = set(normalized_query.split("-"))
    padded_query = f"-{normalized_query}-"
    return [
        tag
        for tag in tags
        if f"-{tag}-" in padded_query or query_parts.intersection(tag.split("-"))
    ]


def _match_label(keyword, matched_tags, semantic=True):
    signals = ["semantic"] if semantic else []
    if keyword:
        signals.append("keyword")
    if matched_tags:
        signals.append("tag")
    return "+".join(signals)


def _order_by_relevance_then_recency(scored, band=RECENCY_RELEVANCE_BAND):
    """Keep relevance dominant, but prefer newest notes inside close bands.

    Items farther apart than `band` never trade places because of their dates.
    """
    by_relevance = sorted(scored, key=lambda item: item.rank_score, reverse=True)
    ordered = []
    index = 0
    while index < len(by_relevance):
        anchor_score = by_relevance[index].rank_score
        end = index + 1
        while (
            end < len(by_relevance)
            and anchor_score - by_relevance[end].rank_score <= band
        ):
            end += 1
        close_group = by_relevance[index:end]
        close_group.sort(
            key=lambda item: (item.info["date"], item.rank_score),
            reverse=True,
        )
        ordered.extend(close_group)
        index = end
    return ordered


def _passes_relevance_floor(item):
    if item.keyword or item.matched_tags:
        return True
    return item.semantic_score >= MIN_SEMANTIC_SCORE


def search(query, limit=10, tags=None, embed_fn=None, model_name=MODEL_NAME):
    """Hybrid relevance ranking, with newest-first ordering for close matches."""
    if not isinstance(query, str) or not query.strip() or limit <= 0:
        return []
    required_tags, _ = notes_store.normalize_tags(tags)
    if tags is not None and not required_tags:
        return []
    required = set(required_tags)

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
    for info in notes_store.iter_note_infos():
        if required and not required.issubset(info["tags"]):
            continue
        path = info["path"]
        try:
            chunk_vectors = get_chunk_vectors(
                path, embed_fn, model_name=model_name, info=info
            )
        except (ValueError, OSError, UnicodeDecodeError):
            continue
        chunk_scores = [
            (cosine(query_vector, chunk["vector"]), chunk)
            for chunk in chunk_vectors
        ]
        if chunk_scores:
            score, best_chunk = max(chunk_scores, key=lambda item: item[0])
            if best_chunk.get("role") == "meta":
                # Title/tag hit: show the start of the body, not an empty slice.
                semantic_context = info["text"]
            else:
                semantic_context = info["text"][
                    best_chunk["start"]:best_chunk["end"]
                ]
        else:
            score, semantic_context = 0.0, info["text"]
        tag_text = " ".join(info["tags"])
        keyword = has_keyword(info["text"] + " " + tag_text, info["title"])
        matched_tags = _matching_tags(query, info["tags"])
        rank_score = score + TAG_MATCH_BOOST * min(len(matched_tags), 2)
        relevant_text = (
            _keyword_context(info["text"], needles) if keyword else semantic_context
        )
        scored.append(
            _ScoredNote(
                rank_score=rank_score,
                semantic_score=score,
                keyword=keyword,
                matched_tags=matched_tags,
                info=info,
                relevant_text=relevant_text,
            )
        )

    scored = [item for item in scored if _passes_relevance_floor(item)]
    scored = _order_by_relevance_then_recency(scored)
    results = [
        _result(
            item.info,
            item.semantic_score,
            item.rank_score,
            _match_label(item.keyword, item.matched_tags),
            item.relevant_text,
            item.matched_tags,
        )
        for item in scored[:limit]
    ]
    # Keyword rescue, within the limit budget: exact-token hits that semantic
    # ranking buried are SWAPPED IN for the lowest-ranked non-keyword results,
    # so rare names the embedding model misses still surface — and the caller
    # never gets more than `limit` results.
    included = {r["path"] for r in results}
    rescue_candidates = [
        item
        for item in scored[limit:]
        if (item.keyword or item.matched_tags)
        and item.info["path"] not in included
    ]
    for item in rescue_candidates:
        # replace the lowest-ranked pure-semantic result currently held
        for i in range(len(results) - 1, -1, -1):
            if results[i]["match"] == "semantic":
                results[i] = _result(
                    item.info,
                    item.semantic_score,
                    item.rank_score,
                    _match_label(item.keyword, item.matched_tags, semantic=False),
                    item.relevant_text,
                    item.matched_tags,
                )
                break
        else:
            break  # nothing left to swap out
    return results
