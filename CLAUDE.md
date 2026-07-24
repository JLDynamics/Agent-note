# Agent-note — notes MCP server

Append-only, AI-organized notes exposed over MCP. The AI is the interface:
you talk, it files. Notes are plain markdown in dated folders under
`~/.notes/` (configurable through `~/.notesrc`), searchable by meaning via
local fastembed embeddings.
Conversation imports save a raw transcript that the server does not rewrite,
then the connected agent extracts durable memory through ordinary
`create_note` calls.

## Tool surface (6 tools, MCP-only)

`create_note`, `import_conversation`, `search`, `list_recent`, `list_tags`,
`read_note` — defined in
[src/notes_mcp/server.py](src/notes_mcp/server.py). No tool edits or deletes an
existing file: updates are new notes carrying the complete updated context;
newest relevant note on a topic wins. Search keeps relevance primary and sorts
close matches (within 0.05) newest-first, so unrelated recent notes do not take
over. Manual file management happens on the filesystem.

Notes use zero to eight normalized tags instead of one fixed category. The
`create_note` description tells the AI to infer the title and 3-8 useful tags,
reuse established tags from `list_tags`, and never ask the user for metadata.
Old category fields are read as legacy tags without rewriting existing files.

## Layout

```
src/notes_mcp/
  server.py        # MCP tool surface (FastMCP)
  conversation_import.py # raw conversation storage (never rewritten by MCP)
  notes_store.py   # append-only storage, frontmatter, dated folders, path guard
  embeddings.py    # chunked hybrid search, tag signals, close-match recency ordering, self-healing vectors
tests/             # pytest; fake embedder for determinism, -m slow for real model
```

## Run

```bash
uv sync
uv run python -m notes_mcp.server   # stdio MCP server
```

`.mcp.json` registers the server with MCP clients (Hermes, Claude Code, …)
using `uv run` so the path survives venv recreation.

## Test

```bash
uv run pytest            # fast suite (fake embeddings)
uv run pytest -m slow    # real-model integration test (~90 MB download)
```

## Conventions

- **Never add edit/delete tools** — the wall is omission. Updates are new
  notes; the filesystem is the manual escape hatch.
- **Never lose a note.** Embedding failure → note still saves, vector is
  self-healed on next search. Embeddings carry a content hash and are written
  atomically, so manual note edits invalidate stale vectors and concurrent
  searches cannot leave partial JSON. Filenames are claimed with an atomic
  exclusive-create so concurrent writers never overwrite each other.
- **Never rewrite raw conversations.** Store exact transcript text under
  `.raw/conversations/<conversation-id>/conversation.txt`; keep metadata in a
  sidecar JSON file. Exclude all `.raw/` content from indexing and `read_note`.
  `import_conversation` only performs this reliable save step; the connected
  agent must then put all derived memory through `create_note`. Do not add an
  MCP sampling dependency: common desktop clients may not implement it.
- **Tests use a fake embedder** (`tests/test_embeddings.py`) for deterministic
  ranking; don't reach for the real model in unit tests.
