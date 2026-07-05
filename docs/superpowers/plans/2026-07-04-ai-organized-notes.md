# AI-Organized Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild notes-mcp as an MCP-only, append-only note system with four tools (`create_note`, `search`, `list_recent`, `read_note`), dated-folder storage, and hybrid semantic+keyword search via local fastembed embeddings.

**Architecture:** Three modules. `notes_store.py` owns the filesystem (dated folders, frontmatter, listing, path-guarded reads). `embeddings.py` owns vectors (lazy fastembed model, cosine similarity, self-healing `.embedding` companions, hybrid search). `server.py` is a thin FastMCP layer exposing exactly four tools. The old CLI (`core.py`, `cli.py`, `test_core.py`, console script) is deleted. Notes are never modified or deleted via MCP — updates are new notes; newest content wins.

**Tech Stack:** Python 3.12, FastMCP (`mcp[cli]`), fastembed (ONNX, model `sentence-transformers/all-MiniLM-L6-v2`, 384-dim), pytest.

## Global Constraints

- Storage root: `~/.notes`, overridable via `~/.notesrc` JSON key `notes_folder` (existing behavior, must keep working).
- New note files: `<root>/YYYY-MM-DD/HH-MM-SS.md`; same-second collision gets `-2`, `-3`, … suffix.
- Categories (exactly these five, anything else = save without category and mention it): `feelings`, `project_notes`, `user_context`, `technical_insights`, `world_knowledge`.
- Embedding companion: same path as note with `.embedding` suffix; JSON `{"model": "<name>", "vector": [...]}`.
- Embedding model name constant: `sentence-transformers/all-MiniLM-L6-v2`. Lazy-loaded — never at import or server startup.
- Search returns FULL note text when note text ≤ 1500 chars, else a 300-char snippet.
- No tool may modify or delete an existing file. Legacy flat notes in the root are read-only inputs.
- Never lose a note: embedding failures must not block a save.
- Tests must not download the model: all search/embedding tests use a fake embed function; one optional real-model test marked `@pytest.mark.slow`.
- Commit after every task (at minimum).

---

### Task 1: `notes_store.py` — folder config, frontmatter, entry creation

**Files:**
- Create: `src/notes_mcp/notes_store.py`
- Test: `tests/test_notes_store.py`

**Interfaces:**
- Produces: `get_notes_folder() -> Path`; `CATEGORIES: frozenset[str]`;
  `parse_frontmatter(text: str) -> tuple[dict, str]`;
  `create_entry(content: str, category: str | None = None, title: str | None = None, now: datetime | None = None) -> tuple[Path, str | None]`
  (returns the created path and a warning string or None).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_notes_store.py
import json
from datetime import datetime
from pathlib import Path

import pytest

from notes_mcp import notes_store


@pytest.fixture
def notes_folder(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(notes_store, "get_notes_folder", lambda: folder)
    return folder


FIXED_NOW = datetime(2026, 7, 4, 14, 30, 52)


def test_create_entry_writes_dated_file(notes_folder):
    path, warning = notes_store.create_entry("Buy milk and eggs", now=FIXED_NOW)
    assert path == notes_folder / "2026-07-04" / "14-30-52.md"
    assert path.exists()
    assert warning is None
    meta, body = notes_store.parse_frontmatter(path.read_text())
    assert body.strip() == "Buy milk and eggs"
    assert meta["date"] == "2026-07-04T14:30:52"
    assert "title" in meta


def test_create_entry_with_category_and_title(notes_folder):
    path, warning = notes_store.create_entry(
        "I prefer simple explanations", category="user_context",
        title="Jack's learning style", now=FIXED_NOW)
    meta, _ = notes_store.parse_frontmatter(path.read_text())
    assert meta["category"] == "user_context"
    assert meta["title"] == "Jack's learning style"
    assert warning is None


def test_create_entry_invalid_category_saves_anyway(notes_folder):
    path, warning = notes_store.create_entry("text", category="nonsense", now=FIXED_NOW)
    assert path.exists()
    meta, _ = notes_store.parse_frontmatter(path.read_text())
    assert "category" not in meta
    assert "nonsense" in warning


def test_create_entry_same_second_collision(notes_folder):
    p1, _ = notes_store.create_entry("first", now=FIXED_NOW)
    p2, _ = notes_store.create_entry("second", now=FIXED_NOW)
    p3, _ = notes_store.create_entry("third", now=FIXED_NOW)
    assert p1.name == "14-30-52.md"
    assert p2.name == "14-30-52-2.md"
    assert p3.name == "14-30-52-3.md"
    assert p1.read_text() != p2.read_text()


def test_parse_frontmatter_no_frontmatter():
    meta, body = notes_store.parse_frontmatter("# Just a heading\n\ntext\n")
    assert meta == {}
    assert body.startswith("# Just a heading")


def test_get_notes_folder_respects_notesrc(tmp_path, monkeypatch):
    custom = tmp_path / "custom_notes"
    rc = tmp_path / ".notesrc"
    rc.write_text(json.dumps({"notes_folder": str(custom)}))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert notes_store.get_notes_folder() == custom
    assert custom.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notes_store.py -v`
Expected: FAIL — `ImportError: cannot import name 'notes_store'` (or ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

```python
# src/notes_mcp/notes_store.py
"""Append-only note storage: dated folders, YAML-ish frontmatter."""
import json
from datetime import datetime
from pathlib import Path

CATEGORIES = frozenset(
    ["feelings", "project_notes", "user_context", "technical_insights", "world_knowledge"]
)


def get_notes_folder():
    """Notes root: ~/.notes, or "notes_folder" from ~/.notesrc if present."""
    config_file = Path.home() / ".notesrc"
    default_folder = Path.home() / ".notes"
    if config_file.exists():
        config = json.loads(config_file.read_text())
        folder = Path(config.get("notes_folder", default_folder)).expanduser()
    else:
        folder = default_folder
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def parse_frontmatter(text):
    """Split a note into (meta dict, body). Tolerates missing frontmatter."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"')
    body = text[end + 4:].lstrip("\n")
    return meta, body


def _default_title(now):
    return now.strftime("%-I:%M:%S %p - %B %-d, %Y")


def create_entry(content, category=None, title=None, now=None):
    """Create a new note file in today's dated folder. Never overwrites.

    Returns (path, warning): warning is set when an invalid category was
    dropped (the note still saves — never lose content over metadata)."""
    now = now or datetime.now()
    folder = get_notes_folder() / now.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)

    warning = None
    if category is not None and category not in CATEGORIES:
        warning = (
            f"Unknown category '{category}' — saved without category. "
            f"Valid: {', '.join(sorted(CATEGORIES))}"
        )
        category = None

    stem = now.strftime("%H-%M-%S")
    path = folder / f"{stem}.md"
    counter = 2
    while path.exists():
        path = folder / f"{stem}-{counter}.md"
        counter += 1

    lines = [
        "---",
        f'title: "{title or _default_title(now)}"',
        f"date: {now.strftime('%Y-%m-%dT%H:%M:%S')}",
    ]
    if category:
        lines.append(f"category: {category}")
    lines += ["---", "", content, ""]
    path.write_text("\n".join(lines))
    return path, warning
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_notes_store.py -v`
Expected: 6 passed. (Old `tests/test_core.py` still passes too — untouched so far.)

- [ ] **Step 5: Commit**

```bash
git add src/notes_mcp/notes_store.py tests/test_notes_store.py
git commit -m "feat: append-only note store — dated folders, frontmatter, safe category handling"
```

---

### Task 2: `notes_store.py` — listing, date resolution, path-guarded reads

**Files:**
- Modify: `src/notes_mcp/notes_store.py` (append functions)
- Test: `tests/test_notes_store.py` (append tests)

**Interfaces:**
- Consumes: Task 1's `get_notes_folder`, `parse_frontmatter`.
- Produces: `iter_note_paths() -> list[Path]` (all .md notes, legacy + dated);
  `note_date(path: Path) -> datetime`;
  `note_info(path: Path) -> dict` with keys `path`(str), `date`(iso str), `title`, `category`, `text`(body);
  `list_recent(days: int = 7, category: str | None = None) -> list[dict]` (newest first);
  `read_note(path_str: str) -> str` (raises `ValueError` outside the notes root).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notes_store.py`:

```python
def _legacy_note(folder, name, text="# Old note\n\nlegacy content\n"):
    p = folder / name
    p.write_text(text)
    return p


def test_iter_note_paths_covers_legacy_and_dated(notes_folder):
    legacy = _legacy_note(notes_folder, "2026-05-14-205701-my-first-note.md")
    new, _ = notes_store.create_entry("new style", now=FIXED_NOW)
    paths = notes_store.iter_note_paths()
    assert legacy in paths and new in paths
    assert all(p.suffix == ".md" for p in paths)


def test_note_date_new_style_and_legacy(notes_folder):
    new, _ = notes_store.create_entry("x", now=FIXED_NOW)
    assert notes_store.note_date(new) == FIXED_NOW
    legacy = _legacy_note(notes_folder, "2026-05-14-205701-my-first-note.md")
    assert notes_store.note_date(legacy) == datetime(2026, 5, 14, 20, 57, 1)


def test_note_date_unparseable_falls_back_to_mtime(notes_folder):
    weird = _legacy_note(notes_folder, "20260513_225818_my_first_note.md")
    got = notes_store.note_date(weird)
    assert got == datetime.fromtimestamp(weird.stat().st_mtime)


def test_list_recent_filters_by_days_and_category(notes_folder, monkeypatch):
    old_now = datetime(2026, 6, 1, 10, 0, 0)
    notes_store.create_entry("old note", now=old_now)
    notes_store.create_entry("fresh plain", now=FIXED_NOW)
    notes_store.create_entry("fresh feeling", category="feelings",
                             now=datetime(2026, 7, 4, 15, 0, 0))
    monkeypatch.setattr(notes_store, "_now", lambda: datetime(2026, 7, 5, 9, 0, 0))

    recent = notes_store.list_recent(days=7)
    texts = [r["text"].strip() for r in recent]
    assert texts == ["fresh feeling", "fresh plain"]  # newest first, no old note

    only_feelings = notes_store.list_recent(days=7, category="feelings")
    assert len(only_feelings) == 1
    assert only_feelings[0]["category"] == "feelings"


def test_read_note_returns_content(notes_folder):
    path, _ = notes_store.create_entry("readable", now=FIXED_NOW)
    assert "readable" in notes_store.read_note(str(path))


def test_read_note_refuses_outside_paths(notes_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private key")
    with pytest.raises(ValueError):
        notes_store.read_note(str(secret))
    with pytest.raises(ValueError):
        notes_store.read_note(str(notes_folder / ".." / "secret.txt"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notes_store.py -v`
Expected: new tests FAIL with `AttributeError: ... has no attribute 'iter_note_paths'`; Task 1 tests still pass.

- [ ] **Step 3: Write the implementation**

Append to `src/notes_mcp/notes_store.py`:

```python
import re

_LEGACY_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})")
_NEW_STEM = re.compile(r"^(\d{2})-(\d{2})-(\d{2})(?:-\d+)?$")
_DAY_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now():
    return datetime.now()


def iter_note_paths():
    return sorted(get_notes_folder().rglob("*.md"))


def note_date(path):
    """Best-effort creation time: dated-folder name, legacy filename, or mtime."""
    stem_match = _NEW_STEM.match(path.stem)
    if stem_match and _DAY_DIR.match(path.parent.name):
        h, m, s = (int(g) for g in stem_match.groups())
        y, mo, d = (int(x) for x in path.parent.name.split("-"))
        return datetime(y, mo, d, h, m, s)
    legacy = _LEGACY_DATE.match(path.name)
    if legacy:
        y, mo, d, h, m, s = (int(g) for g in legacy.groups())
        return datetime(y, mo, d, h, m, s)
    return datetime.fromtimestamp(path.stat().st_mtime)


def note_info(path):
    meta, body = parse_frontmatter(path.read_text())
    return {
        "path": str(path),
        "date": note_date(path).isoformat(),
        "title": meta.get("title", path.stem),
        "category": meta.get("category"),
        "text": body,
    }


def list_recent(days=7, category=None):
    from datetime import timedelta

    cutoff = _now() - timedelta(days=days)
    infos = [note_info(p) for p in iter_note_paths() if note_date(p) >= cutoff]
    if category:
        infos = [i for i in infos if i["category"] == category]
    return sorted(infos, key=lambda i: i["date"], reverse=True)


def read_note(path_str):
    """Read one note by path. Refuses anything outside the notes root."""
    root = get_notes_folder().resolve()
    path = Path(path_str).expanduser().resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Refused: {path_str} is outside the notes folder")
    return path.read_text()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_notes_store.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/notes_mcp/notes_store.py tests/test_notes_store.py
git commit -m "feat: note listing, date resolution, path-guarded reads"
```

---

### Task 3: `embeddings.py` — companion files, self-healing, cosine

**Files:**
- Create: `src/notes_mcp/embeddings.py`
- Test: `tests/test_embeddings.py`

**Interfaces:**
- Consumes: `notes_store.note_info`, `notes_store.parse_frontmatter`.
- Produces: `MODEL_NAME: str`; `embed_text(text: str) -> list[float]` (real model, lazy);
  `cosine(a: list[float], b: list[float]) -> float`;
  `embedding_path(note_path: Path) -> Path`;
  `save_embedding(note_path: Path, vector: list[float], model_name: str = MODEL_NAME) -> None`;
  `get_vector(note_path: Path, embed_fn, model_name: str = MODEL_NAME) -> list[float]` (self-healing);
  `try_embed_note(note_path: Path, embed_fn=None) -> bool` (best-effort, never raises).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_embeddings.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_embeddings.py -v`
Expected: FAIL — `ImportError: cannot import name 'embeddings'`.

- [ ] **Step 3: Write the implementation**

```python
# src/notes_mcp/embeddings.py
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
```

Note: `try_embed_note` with the default `embed_fn` writes under `MODEL_NAME`; tests always pass an explicit fake and matching `model_name` via `get_vector`, or rely on `try_embed_note`'s failure path — no real model is ever loaded in tests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_embeddings.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/notes_mcp/embeddings.py tests/test_embeddings.py
git commit -m "feat: embedding companions with self-healing and lazy fastembed model"
```

---

### Task 4: hybrid search in `embeddings.py`

**Files:**
- Modify: `src/notes_mcp/embeddings.py` (append)
- Test: `tests/test_embeddings.py` (append)

**Interfaces:**
- Consumes: Task 2's `iter_note_paths`/`note_info`, Task 3's `get_vector`/`cosine`.
- Produces: `search(query: str, limit: int = 10, category: str | None = None, embed_fn=None, model_name: str = MODEL_NAME) -> list[dict]` — each dict: `path`, `date`, `title`, `category`, `score` (float), `match` (`"semantic"` | `"keyword"` | `"semantic+keyword"`), `text` (full body if ≤ 1500 chars, else 300-char snippet), `truncated` (bool).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_embeddings.py`:

```python
def test_search_ranks_semantically(notes_folder):
    notes_store.create_entry("milk food milk food shopping")
    notes_store.create_entry("python code refactoring tips")
    results = embeddings.search("milk food", embed_fn=fake_embed,
                                model_name="fake-model")
    assert "milk" in results[0]["text"]
    assert results[0]["score"] >= results[-1]["score"]


def test_search_keyword_rescues_exact_token(notes_folder):
    # fake_embed gives "OpenClaw" no signal at all — keyword match must find it
    notes_store.create_entry("OpenClaw gateway restart instructions")
    notes_store.create_entry("milk food")
    results = embeddings.search("OpenClaw", limit=2, embed_fn=fake_embed,
                                model_name="fake-model")
    hit = [r for r in results if "OpenClaw" in r["text"]]
    assert hit and "keyword" in hit[0]["match"]


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_embeddings.py -v`
Expected: new tests FAIL with `AttributeError: ... has no attribute 'search'`.

- [ ] **Step 3: Write the implementation**

Append to `src/notes_mcp/embeddings.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_embeddings.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/notes_mcp/embeddings.py tests/test_embeddings.py
git commit -m "feat: hybrid semantic+keyword search with category filter and snippets"
```

---

### Task 5: new server surface; delete CLI, core, and old tests

**Files:**
- Modify: `src/notes_mcp/server.py` (full rewrite)
- Modify: `pyproject.toml` (remove `[project.scripts]`, add `fastembed`)
- Delete: `src/notes_mcp/core.py`, `src/notes_mcp/cli.py`, `tests/test_core.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: everything above.
- Produces: MCP tools `create_note(content, category=None, title=None)`, `search(query, limit=10, category=None)`, `list_recent(days=7, category=None)`, `read_note(path)` — all returning JSON strings (structured data for the AI, no parsing ambiguity).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
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
```

Note: the fixture replaces `embeddings.embed_text` with a fake, so `create_note`'s best-effort embed step succeeds deterministically in tests — the `.embedding` existence assertion is safe. (`try_embed_note` calls `get_vector`, which calls the module-level `embed_text` that the fixture patched. For that to hold, `try_embed_note`'s default must resolve `embed_text` at call time — the Task 3 implementation does: `embed_fn or embed_text` runs inside the function body.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL — `AttributeError: module 'notes_mcp.server' has no attribute 'TOOL_NAMES'` (old server still loaded).

- [ ] **Step 3: Rewrite the server**

Replace the entire contents of `src/notes_mcp/server.py`:

```python
"""Notes MCP server — append-only AI-organized notes.

Four tools only. No tool modifies or deletes an existing file: updates are
new notes carrying the complete updated context; newest content wins.
"""
import json

from mcp.server.fastmcp import FastMCP

from notes_mcp import embeddings, notes_store

mcp = FastMCP("notes")

TOOL_NAMES = ("create_note", "search", "list_recent", "read_note")

_CATEGORIES_DOC = ", ".join(sorted(notes_store.CATEGORIES))


@mcp.tool()
def create_note(content: str, category: str = None, title: str = None) -> str:
    """Save a new note. Notes are append-only: to UPDATE existing knowledge,
    create a new note containing the COMPLETE updated context (never just the
    change) — the newest note on a topic wins. Optional category, one of:
    feelings, project_notes, user_context, technical_insights, world_knowledge."""
    path, warning = notes_store.create_entry(content, category=category, title=title)
    embeddings.try_embed_note(path)
    return json.dumps({"path": str(path), "warning": warning})


@mcp.tool()
def search(query: str, limit: int = 10, category: str = None) -> str:
    """Hybrid semantic + keyword search over ALL notes. Results may include
    older notes on the same topic — read dates carefully: the NEWEST content
    is authoritative, older results are history. Short notes include full
    text; truncated ones need read_note. Optional category filter."""
    results = embeddings.search(query, limit=limit, category=category)
    return json.dumps(results)


@mcp.tool()
def list_recent(days: int = 7, category: str = None) -> str:
    """List notes from the last N days, newest first. Optional category
    filter (one of: feelings, project_notes, user_context,
    technical_insights, world_knowledge)."""
    return json.dumps(notes_store.list_recent(days=days, category=category))


@mcp.tool()
def read_note(path: str) -> str:
    """Read the full markdown of one note, by a path returned from search or
    list_recent. Only paths inside the notes folder are allowed."""
    try:
        return notes_store.read_note(path)
    except (ValueError, FileNotFoundError) as exc:
        return f"Refused or not found: {exc}"


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Delete the old app and update packaging**

```bash
git rm src/notes_mcp/core.py src/notes_mcp/cli.py tests/test_core.py
```

Edit `pyproject.toml`: delete the two lines

```toml
[project.scripts]
notes = "notes_mcp.cli:main"
```

and change dependencies to:

```toml
dependencies = [
    "mcp[cli]>=1.27.2",
    "fastembed>=0.6",
]
```

Then run: `uv sync --group dev`
Expected: resolves and installs fastembed without error.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass (notes_store + embeddings + server); `test_core.py` no longer exists.

- [ ] **Step 6: Smoke-test the server starts**

Run: `timeout 5 uv run python -c "from notes_mcp import server; print('tools:', server.TOOL_NAMES)"`
Expected: `tools: ('create_note', 'search', 'list_recent', 'read_note')` — instantly (no model load at import).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat!: MCP-only four-tool surface; remove CLI, core, and editing tools"
```

---

### Task 6: optional real-model integration test

**Files:**
- Test: `tests/test_integration.py`
- Modify: `pyproject.toml` (register the `slow` marker)

**Interfaces:**
- Consumes: `embeddings.embed_text`, `embeddings.search`.

- [ ] **Step 1: Write the test**

```python
# tests/test_integration.py
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
```

- [ ] **Step 2: Register the marker and default exclusion**

In `pyproject.toml`, replace the `[tool.pytest.ini_options]` section with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: real-model tests (downloads ~90 MB); run with -m slow"]
addopts = "-m 'not slow'"
```

- [ ] **Step 3: Verify exclusion and (optionally) the real test**

Run: `uv run pytest -v`
Expected: all fast tests pass; integration test shown as deselected.

Run (optional, needs network the first time): `uv run pytest -m slow -v`
Expected: 1 passed (takes ~1 min on first run for the model download).

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py pyproject.toml
git commit -m "test: optional real-model semantic search integration test"
```

---

### Task 7: README rewrite + deployment (CLAUDE.md snippet, model pre-download, uninstall old CLI)

**Files:**
- Modify: `README.md` (full rewrite)
- Modify: `~/.claude/CLAUDE.md` (replace the "Notes CLI" section — OUTSIDE the repo; do this only with the user present)

**Interfaces:**
- Consumes: the finished tool surface from Task 5.

- [ ] **Step 1: Rewrite README.md**

Replace the entire contents of `README.md`:

````markdown
# Notes MCP Server

An append-only, AI-organized note system exposed as an
[MCP](https://modelcontextprotocol.io) server. The AI is the interface:
you talk, it files. Notes are markdown in dated folders under `~/.notes/`,
searchable by meaning via local embeddings (fastembed — nothing leaves
your machine).

**Update model:** notes are never edited or deleted. An update is a new
note carrying the complete updated context; the newest note on a topic
wins. Old notes remain as searchable history. Manual file management
(deleting, editing) happens directly on the filesystem — every note is
plain markdown.

## Layout

```
~/.notes/
  2026-07-04/
    14-30-52.md          # one note
    14-30-52.embedding   # its search vector (auto-regenerated if lost)
```

Configure a different root in `~/.notesrc`: `{"notes_folder": "~/MyNotes"}`.

## Tools

| Tool | Purpose |
|---|---|
| `create_note(content, category?, title?)` | Save a new note (append-only) |
| `search(query, limit?, category?)` | Hybrid semantic + keyword search |
| `list_recent(days?, category?)` | Recent notes, newest first |
| `read_note(path)` | Full text of one note (paths from search/list) |

Categories: `feelings`, `project_notes`, `user_context`,
`technical_insights`, `world_knowledge`.

## Install

```bash
uv sync
# pre-download the embedding model so the first search is instant:
uv run python -c "from notes_mcp.embeddings import embed_text; embed_text('warm up')"
```

MCP config (`.mcp.json` or Claude Code settings):

```json
{"mcpServers": {"notes": {"command": "uv", "args": ["run", "python", "-m", "notes_mcp.server"], "cwd": "<path-to-this-repo>"}}}
```

Optional: `git init ~/.notes` for free append-only history of every note.

## Recommended global CLAUDE.md section

Replace any old "Notes CLI" section in `~/.claude/CLAUDE.md` with:

```markdown
## Notes (MCP)

I manage notes ONLY through the notes MCP tools (create_note, search,
list_recent, read_note). Notes are append-only.

- **Save flow:** when I ask to save anything (idea, learning, text, or a
  linked article to summarize): gather the content (ask a follow-up or
  fetch the article), pick a category, create_note. Then read it back and
  offer to discuss/develop the idea with your own insights. When the
  discussion ends, create_note again with the COMPLETE updated context
  including a summary of the discussion.
- **Recall flow:** when I ask about something saved: search, read the
  results newest-first — the newest note on a topic is the truth, older
  ones are history. Offer the same discuss/develop engagement; on finish,
  create_note with the complete updated context.
- **Update discipline:** never save fragments. Every new note on an
  existing topic must stand alone as the current, complete truth of it.
```

## Tests

```bash
uv run pytest            # fast suite (fake embeddings)
uv run pytest -m slow    # real-model integration test (~90 MB download)
```
````

- [ ] **Step 2: Verify the README's install command works**

Run: `uv run python -c "from notes_mcp.embeddings import embed_text; print(len(embed_text('warm up')))"`
Expected: `384` (downloads the model on first run; instant after).

- [ ] **Step 3: Deployment (with the user)**

```bash
# remove the old terminal command:
uv tool uninstall notes-mcp
```

Then edit `~/.claude/CLAUDE.md`: delete the old "## Notes CLI" section and paste the new "## Notes (MCP)" section from the README. Ask the user before touching their global file. Optionally: `git init ~/.notes && cd ~/.notes && git add -A && git commit -m "initial notes snapshot"`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README for append-only MCP-only notes; CLAUDE.md workflow snippet"
```

---

## Self-Review Notes

- **Spec coverage:** storage/format → Tasks 1–2; four tools → Task 5; hybrid search + category filter + full-text/snippet → Task 4; self-healing/backfill + lazy model + model-name stamp → Task 3; wall by omission → Task 5 (deletions + `test_tool_surface_is_exactly_four`); behavior layer + deployment (pre-download, git init, CLI uninstall, CLAUDE.md) → Task 7; never-lose-a-note → `try_embed_note` + invalid-category tests.
- **Type consistency:** `note_info` dict keys (`path`, `date`, `title`, `category`, `text`) are consumed verbatim by `_result` and the server's JSON; `create_entry` returns `(Path, str|None)` and `server.create_note` serializes both.
- **Placeholder scan:** clean — no TBDs, no "similar to Task N", every code step shows the code.
