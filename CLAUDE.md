# Agent-note — notes MCP server

Append-only, AI-organized notes exposed over MCP. The AI is the interface:
you talk, it files. Notes are plain markdown in dated folders under
`~/.notes/` (configurable via `~/.notesrc`), searchable by meaning via local
fastembed embeddings (nothing leaves the machine).

## Tool surface (4 tools, MCP-only)

`create_note`, `search`, `list_recent`, `read_note` — defined in
[src/notes_mcp/server.py](src/notes_mcp/server.py). No tool edits or deletes
an existing file: updates are new notes carrying the complete updated
context; newest note on a topic wins. Manual file management happens on the
filesystem.

Categories: `feelings`, `project_notes`, `user_context`,
`technical_insights`, `world_knowledge`. The `create_note` docstring tells
the AI to infer category and title itself — never ask the user.

## Layout

```
src/notes_mcp/
  server.py        # MCP tool surface (FastMCP)
  notes_store.py   # append-only storage, frontmatter, dated folders, path guard
  embeddings.py    # fastembed wrapper, hybrid (semantic + keyword) search, self-healing vectors
tests/             # pytest; fake embedder for determinism, -m slow for real model
docs/superpowers/  # design spec and plan
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
  self-healed on next search.
- **Tests use a fake embedder** (`tests/test_embeddings.py`) for deterministic
  ranking; don't reach for the real model in unit tests.