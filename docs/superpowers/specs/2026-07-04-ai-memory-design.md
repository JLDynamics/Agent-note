# Unified Notes + AI Memory for notes-mcp — Design

**Date:** 2026-07-04
**Status:** Approved pending final review
**Inspired by:** [private-journal-mcp](https://github.com/obra/private-journal-mcp)

## Goal

Evolve notes-mcp into ONE unified system holding two kinds of entries:

- **Notes** — content the user asks to save. Title-named, editable, deletable.
  The existing personal-notes features carry over as this editing layer.
- **Memories** — observations the AI records for itself via `process_thoughts`.
  Time-named, write-once, scoped to project or user.

One semantic search covers everything. The user's interface is conversation
with the AI; the CLI remains as-is for manual use.

## Scope

**In:** structured memory writing, unified semantic search (notes + memories),
dual scopes for memories, chronological listing, single-entry reads, existing
note tools retained.

**Out:** vector databases, cloud embedding APIs, editing/deleting memory
entries via tools, project-scoped user notes (all user notes stay in the
user-scope folder, as today).

## Architecture

```
src/notes_mcp/
  core.py        # existing note storage/editing — behavior unchanged
  memory.py      # NEW: memory scopes, entry write/read/list
  embeddings.py  # NEW: fastembed wrapper, cosine similarity, unified search
  server.py      # note tools (kept) + memory tools + unified search
  cli.py         # unchanged
```

`core.py` functions are reused as the notes editing layer. `memory.py` handles
memory entries only. Neither imports the other; `embeddings.py` and `server.py`
sit above both.

## Storage

```
~/.notes/                            # user scope root (existing folder)
  {timestamp}-{slug}.md              # user notes — existing format, untouched
  memories/YYYY-MM-DD/HH-MM-SS.md    # AI memories, user scope
<project>/.project-notes/
  memories/YYYY-MM-DD/HH-MM-SS.md    # AI memories, project scope
```

- No migration: existing notes are already in place. `~/.notesrc`
  (`notes_folder`) keeps working and relocates the whole user scope.
- Memory entry: markdown, YAML frontmatter (`date` ISO 8601, section names).
  Each section rendered as a `## Heading`.
- Companion `.embedding` file beside EVERY entry (notes and memories): JSON
  with `model` name and `vector` (list of floats).
- Project root = server working directory at startup; if that is the user's
  home directory or filesystem root, project memories fall back to user scope.
- Directories created on first write. On first creation of `.project-notes/`,
  append it to the project's `.gitignore` (create if absent, skip if present).
- Memory filename collision (same second, same scope): append `-2`, `-3`, ...

## MCP Tools

### Kept note tools (existing behavior, unchanged)

`create_note`, `show_note`, `list_notes`, `count_notes`, `delete_note`,
`tag_note`, `append_note`, `replace_section`, `insert_after_heading`.

Changes around them:
- After any note write (create/append/replace/insert/tag), re-embed the note
  and update its `.embedding`. After `delete_note`, remove its `.embedding`.
- `search_notes` (keyword) is REMOVED from the MCP server, replaced by unified
  `search` below. The function stays in `core.py` for the CLI.

### `process_thoughts` — NEW

Five optional string arguments; at least one required (else a friendly error):

| Section | Scope |
|---|---|
| `project_notes` | project |
| `technical_insights` | project |
| `feelings` | user |
| `user_context` | user |
| `world_knowledge` | user |

Writes one entry per scope that received content (max two files per call),
embeds each after saving.

### `search(query, limit=10, type="all", scope="all")` — NEW

Unified semantic search over notes AND memories. `type`: `"note"`, `"memory"`,
or `"all"`. `scope` (memories only): `"project"`, `"user"`, `"all"`. Embeds the
query, ranks all candidate `.embedding` vectors by cosine similarity, returns
top `limit`: path, kind (note/memory), scope, date, title (notes) or sections
(memories), similarity score, snippet.

### `list_recent(days=7, type="all")` — NEW

Notes and/or memories from the last `days` days, newest first, with
path/kind/date/title.

### `read_memory_entry(path)` — NEW

Full markdown of one memory entry. **Path guard:** resolves the path and
refuses anything not inside a memory directory. (Notes are read via the
existing `show_note`.)

## Tool-choice rule (baked into tool descriptions)

- Note tools: "the user's notes — use when the user asks to save, find, or
  edit their content."
- `process_thoughts`: "the assistant's own memory — record your observations,
  insights, and decisions; not for content the user asked to save as a note."
- When the user says "remember this," treat it as a memory (`user_context` or
  `project_notes` as appropriate).

Memory is opt-in by the AI, not automatic recording. Recommend a one-line
standing instruction in the user's CLAUDE.md after deployment (e.g. "As you
work, record insights and decisions with process_thoughts") to get
continuous journaling behavior.

## Embeddings

- Library: `fastembed` (ONNX, no PyTorch), model `all-MiniLM-L6-v2` (384-dim).
  One-time ~90 MB model download on first use, then fully offline.
- Lazy initialization: model loads on the first tool call that needs it.
- `embeddings.py` exposes `embed_text(text) -> list[float]` and
  `search(query, candidates) -> ranked results`. Cosine similarity as a plain
  function (no numpy at this scale).
- Every `.embedding` records the model name. On search, a missing, corrupt, or
  model-mismatched embedding is regenerated from the markdown (self-healing).
  This also backfills notes created via the CLI or edited by hand.

## Error Handling

Theme: never lose a thought.

- Embedding failure (e.g. offline first run): the entry/note still saves;
  embedding is backfilled by self-healing on a later search.
- Corrupt/missing `.embedding`: regenerate from markdown.
- All-empty `process_thoughts` call: error message, nothing written.
- `read_memory_entry` outside memory dirs: refusal message.

## Testing

- pytest, existing pattern: storage pointed at temp folders via monkeypatching.
- Unit: section→scope routing, memory file format, gitignore append, collision
  suffix, path guard, recency filter, re-embed on note edit, embedding cleanup
  on note delete.
- Search: fake embedder (stub returning fixed vectors) for fast, offline,
  deterministic ranking tests, including type/scope filters and model-mismatch
  regeneration.
- One optional integration test with real fastembed, marked slow/skippable.
- Existing `test_core.py` suite must keep passing untouched.

## Dependencies

- `fastembed` added to `pyproject.toml`. Acceptable for CLI installs for now;
  revisit as an optional extra if the package is published.

## Build Order (suggested)

1. `memory.py`: scopes + entry writing + `process_thoughts` (no embeddings yet)
2. `list_recent` + `read_memory_entry` with path guard
3. `embeddings.py` + embedding-on-write (notes and memories) + unified
   `search` + self-healing + remove `search_notes` from server
