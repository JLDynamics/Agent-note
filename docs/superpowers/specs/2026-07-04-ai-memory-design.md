# AI Memory for notes-mcp — Design

**Date:** 2026-07-04
**Status:** Approved pending final review
**Inspired by:** [private-journal-mcp](https://github.com/obra/private-journal-mcp)

## Goal

Turn notes-mcp into an AI memory system: Claude (or any MCP client) can record
structured thoughts during a session and recall them later by meaning, scoped to
either the current project or the user globally. The existing personal-notes
features (CLI and MCP) are unchanged.

## Scope

**In:** structured writing tool, semantic search over memories, dual storage
scopes, chronological listing, single-entry reads. MCP-only — no CLI commands.

**Out:** semantic search over personal `~/.notes` notes (they keep keyword
search), vector databases, cloud embedding APIs, editing/deleting memory
entries via tools (files can be managed by hand).

## Architecture

New modules; existing code untouched except `server.py` gaining tools:

```
src/notes_mcp/
  core.py        # existing personal notes — unchanged
  memory.py      # NEW: scope resolution, entry write/read/list
  embeddings.py  # NEW: fastembed wrapper, cosine similarity, search
  server.py      # + 4 new MCP tools
  cli.py         # unchanged
```

## Storage

```
<project>/.project-notes-memory/YYYY-MM-DD/HH-MM-SS.md    # project scope
~/.private-notes-memory/YYYY-MM-DD/HH-MM-SS.md            # user scope
```

- Entry: markdown, YAML frontmatter with `title`, `date` (ISO 8601), and the
  section names it contains. Each section rendered as a `## Heading`.
- Companion file `HH-MM-SS.embedding` beside each entry: JSON with `model`
  (embedding model name) and `vector` (list of floats).
- Project root = the MCP server process's working directory at startup. If that
  directory is the user's home directory or the filesystem root (i.e. the server
  wasn't started inside a real project), project-scoped content falls back to
  the user scope (never error, never lose a thought).
- Directories are created on first write, not at startup.
- On first creation of `.project-notes-memory/`, append it to the project's
  `.gitignore` (create the file if absent; skip if the line is already there).
- Filename collision (same second, same scope): append `-2`, `-3`, etc.

## MCP Tools

### `process_thoughts`

Five optional string arguments; at least one required (else a friendly error):

| Section | Scope |
|---|---|
| `project_notes` | project |
| `technical_insights` | project |
| `feelings` | user |
| `user_context` | user |
| `world_knowledge` | user |

Writes one entry per scope that received content (max two files per call).
Embeds each entry after saving. Tool description documents each section's
purpose — that description is what drives correct routing by the AI.

### Disambiguation vs. personal notes

Both feature sets coexist, so tool descriptions must state the dividing rule
explicitly (this is the primary defense against the AI picking the wrong tool):

- `create_note` / `search_notes` etc.: "the user's personal notes — use when
  the user explicitly asks to save, find, or edit a note."
- `process_thoughts` / `search_memories` etc.: "the assistant's own memory —
  use to record or recall your own observations and insights; not for content
  the user asked to save as a note."

Recommend a matching one-line rule in the user's CLAUDE.md after deployment.

### `search_memories(query, limit=10, scope="both")`

Semantic search. `scope` is `"project"`, `"user"`, or `"both"`. Embeds the
query, loads all `.embedding` files in the selected scope(s), ranks by cosine
similarity, returns top `limit` results: path, scope label, date, similarity
score, and a text snippet.

### `list_recent_memories(days=7, scope="both")`

Entries from the last `days` days, newest first, with path/scope/date/title.

### `read_memory_entry(path)`

Returns full markdown of one entry. **Path guard:** resolves the path and
refuses anything not inside one of the two memory directories.

## Embeddings

- Library: `fastembed` (ONNX runtime, no PyTorch), model `all-MiniLM-L6-v2`
  (384-dim). Model downloads once on first use (~90 MB), then fully offline.
- Lazy initialization: the model loads on first tool call that needs it, not at
  server startup.
- `embeddings.py` exposes: `embed_text(text) -> list[float]` and
  `search(query, candidates) -> ranked results`. Cosine similarity implemented
  as a plain function (no numpy dependency needed at this scale).
- Every `.embedding` file records the model name. On search, a mismatched or
  missing/corrupt embedding is regenerated from the markdown (self-healing);
  entries are never skipped silently.

## Error Handling

Theme: never lose a thought.

- Embedding failure (e.g. first-run download offline): entry still saves;
  embedding is backfilled by the self-healing path on a later search.
- Corrupt/missing `.embedding`: regenerate from markdown.
- All-empty `process_thoughts` call: error message, nothing written.
- `read_memory_entry` outside memory dirs: refusal message.

## Testing

- pytest, following the existing suite's pattern: memory dirs pointed at temp
  folders via monkeypatching.
- Unit: section→scope routing, entry file format, frontmatter, gitignore
  append, collision suffix, path guard, recency filter.
- Search: fake embedder (stub returning fixed vectors) for fast, offline,
  deterministic ranking tests; model-mismatch regeneration covered with the
  stub too.
- One optional integration test with real fastembed, marked slow/skippable.

## Dependencies

- `fastembed` added to `pyproject.toml` dependencies. Acceptable for CLI
  installs for now; revisit as an optional extra if the package is published.

## Build Order (suggested)

1. `memory.py` scopes + entry writing + `process_thoughts` (no embeddings yet)
2. `list_recent_memories` + `read_memory_entry` with path guard
3. `embeddings.py` + embedding-on-write + `search_memories` + self-healing
