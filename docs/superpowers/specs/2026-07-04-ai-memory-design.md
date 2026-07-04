# Unified Notes + AI Memory for notes-mcp — Design

**Date:** 2026-07-04
**Status:** Approved pending final review
**Inspired by:** [private-journal-mcp](https://github.com/obra/private-journal-mcp)

## Goal

Evolve notes-mcp into ONE unified system where the AI is the primary
interface. Two kinds of entries:

- **Notes** — content the user asks to save (ideas, learnings, texts, article
  summaries). Title-named, editable, deletable. The AI classifies every note:
  scope (user vs project) and category. Notes are living documents that grow
  as the user discusses them.
- **Memories** — observations the AI records for itself via `process_thoughts`.
  Time-named, write-once.

One semantic search covers everything. The CLI remains for manual use.

## Scope

**In:** structured memory writing, unified semantic search, dual scopes for
BOTH notes and memories, AI classification (scope + category) of notes,
chronological listing, single-entry reads, existing note editing retained,
behavior layer (save/recall workflows) via user's global CLAUDE.md.

**Out:** vector databases, cloud embedding APIs, editing/deleting memory
entries via tools.

## Architecture

```
src/notes_mcp/
  core.py        # note storage/editing; gains optional folder parameter
  memory.py      # NEW: memory scopes, entry write/read/list
  embeddings.py  # NEW: fastembed wrapper, cosine similarity, unified search
  server.py      # note tools (scope-aware) + memory tools + unified search
  cli.py         # unchanged (defaults to user scope, as today)
```

`core.py` functions gain an optional `folder` argument defaulting to the
current user notes folder — existing behavior and CLI are unchanged by
default; the MCP server passes the project folder when scope is "project".

## Storage

```
~/.notes/                            # user scope root (existing folder)
  {timestamp}-{slug}.md              # user-scoped notes — existing format
  memories/YYYY-MM-DD/HH-MM-SS.md    # AI memories, user scope
<project>/.project-notes/
  {timestamp}-{slug}.md              # project-scoped notes
  memories/YYYY-MM-DD/HH-MM-SS.md    # AI memories, project scope
```

- No migration: existing notes are already user-scoped. `~/.notesrc`
  (`notes_folder`) keeps working and relocates the user scope.
- Note frontmatter: existing `tags` plus new `category` — one of `feelings`,
  `project_notes`, `user_context`, `technical_insights`, `world_knowledge` —
  chosen by the AI when saving.
- Memory entry: markdown, YAML frontmatter (`date` ISO 8601, section names),
  sections rendered as `## Heading`.
- Companion `.embedding` file beside EVERY entry (notes and memories): JSON
  with `model` name and `vector`.
- Project root = server working directory at startup; if that is the user's
  home directory or filesystem root, project scope falls back to user scope.
- Directories created on first write. On first creation of `.project-notes/`,
  append it to the project's `.gitignore` (create if absent, skip if present).
- Memory filename collision (same second, same scope): append `-2`, `-3`, ...

## MCP Tools

### Note tools (existing, now scope-aware)

`create_note` gains optional `scope` ("user" default | "project") and
`category` arguments. Lookup-based tools (`show_note`, `delete_note`,
`tag_note`, `append_note`, `replace_section`, `insert_after_heading`) search
BOTH scopes when finding a note by title (user scope first, then project).
`list_notes` / `count_notes` cover both scopes with scope labels.

After any note write, re-embed the note and update its `.embedding`. After
`delete_note`, remove its `.embedding`.

`search_notes` (keyword) is REMOVED from the MCP server, replaced by unified
`search`. The function stays in `core.py` for the CLI.

### `process_thoughts` — NEW

Five optional string arguments; at least one required (else a friendly error):

| Section | Scope |
|---|---|
| `project_notes`, `technical_insights` | project |
| `feelings`, `user_context`, `world_knowledge` | user |

Writes one entry per scope that received content (max two files per call),
embeds each after saving.

### `search(query, limit=10, type="all", scope="all")` — NEW

Unified semantic search over notes AND memories. `type`: `"note"` | `"memory"`
| `"all"`. `scope`: `"project"` | `"user"` | `"all"`. Embeds the query, ranks
all candidate `.embedding` vectors by cosine similarity, returns top `limit`:
path, kind, scope, date, title/category (notes) or sections (memories),
similarity score, snippet.

### `list_recent(days=7, type="all")` — NEW

Notes and/or memories from the last `days` days, newest first.

### `read_memory_entry(path)` — NEW

Full markdown of one memory entry. **Path guard:** refuses paths outside the
memory directories. (Notes are read via `show_note`.)

## Behavior layer — user's global CLAUDE.md (deployment step)

The server provides tools; the workflows below are driven by a standing
section in the user's global `~/.claude/CLAUDE.md` (NOT the repo's project
CLAUDE.md — the workflows must apply in every session). The repo README
documents the recommended snippet. Three behaviors:

**Save workflow.** When the user asks to save anything (a note, an idea, a
learning, a text, a linked article to summarize): gather the content (ask a
follow-up or fetch the article if needed), decide scope (about the user →
user; about the current project → project), pick the category, save via
`create_note`. Then read the saved note back and offer to discuss, develop,
or extend the idea, contributing insights. When the discussion finishes,
append a summary of the conversation to the same note.

**Recall workflow.** When the user asks about something they saved: use
`search` to find matching notes, read them, then offer the same
discuss/develop/extend engagement. When finished, append the new discussion's
summary to the same note. Notes accumulate thinking over time.

**Journaling.** As the AI works, record its own insights, decisions, and
things learned about the user or project with `process_thoughts`. Memory is
opt-in by the AI, not automatic recording; this instruction is what makes it
continuous.

Tool descriptions also carry the dividing rule: note tools for content the
user asked to save; `process_thoughts` for the AI's own observations
("remember this" → memory).

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

- Embedding failure (e.g. offline first run): the entry still saves;
  embedding is backfilled by self-healing on a later search.
- Corrupt/missing `.embedding`: regenerate from markdown.
- All-empty `process_thoughts` call: error message, nothing written.
- `read_memory_entry` outside memory dirs: refusal message.
- Note title found in both scopes: prefer user scope; mention the other match
  in the tool response so the AI can disambiguate.

## Testing

- pytest, existing pattern: storage pointed at temp folders via monkeypatching.
- Unit: section→scope routing, category frontmatter, two-scope note lookup
  (incl. both-scopes collision), memory file format, gitignore append,
  filename collision suffix, path guard, recency filter, re-embed on note
  edit, embedding cleanup on note delete.
- Search: fake embedder (stub with fixed vectors) for fast, offline,
  deterministic ranking tests, including type/scope filters and model-mismatch
  regeneration.
- One optional integration test with real fastembed, marked slow/skippable.
- Existing `test_core.py` suite must keep passing (default-folder behavior
  unchanged).

## Dependencies

- `fastembed` added to `pyproject.toml`. Acceptable for CLI installs for now;
  revisit as an optional extra if the package is published.

## Build Order (suggested)

1. `core.py` folder parameter + scope-aware note tools + category frontmatter
2. `memory.py`: scopes + entry writing + `process_thoughts`
3. `list_recent` + `read_memory_entry` with path guard
4. `embeddings.py` + embedding-on-write + unified `search` + self-healing +
   remove `search_notes` from server
5. README: recommended global-CLAUDE.md behavior snippet (save workflow,
   recall workflow, journaling)
