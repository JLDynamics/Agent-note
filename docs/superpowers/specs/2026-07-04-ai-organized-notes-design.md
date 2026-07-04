# AI-Organized Notes for notes-mcp — Design

**Date:** 2026-07-04
**Status:** Approved pending final review
**Model:** append-only notes with semantic recall, adapted from
[private-journal-mcp](https://github.com/obra/private-journal-mcp)'s file
structure and search — applied to a private user note system (no AI
self-journaling layer, single user scope).

## Goal

The AI is the user's note librarian over an append-only store:

- **Save flow:** user asks to save anything (idea, learning, text, linked
  article). The AI gathers content, picks a category, creates a note, then
  offers to discuss and develop the idea. When the discussion finishes, the
  AI creates a NEW note containing the full updated context.
- **Recall flow:** user asks about something saved. The AI finds it via
  semantic search (which returns current and past similar notes with dates),
  treats the newest content as authoritative, offers the same
  discuss/develop engagement, and writes the outcome as a new complete note.

**Update model — no edits, no links:** notes are never modified, deleted, or
explicitly linked. An update is a new note carrying the COMPLETE updated
context (never just the delta). Recency resolves conflicts: when search
returns overlapping content, newest wins — a judgment the AI makes by
reading dated results, not a mechanical link.

## Scope

**In:** append-only note creation with category frontmatter, semantic search,
recency listing, path-based note reading, behavior workflows via the user's
global CLAUDE.md.

**Out (explicitly):** the CLI (deleted), editing/deleting/tagging tools,
note titles as lookup keys, slugs, version links (`supersedes`), dual
storage scopes, the AI self-journaling layer (`process_thoughts`), vector
databases, cloud embedding APIs.

## Architecture

MCP-only. `core.py` and `cli.py` are DELETED, along with the `notes` console
script in `pyproject.toml` (deployment note: `uv tool uninstall` the old CLI
and remove the Notes CLI section from the user's global CLAUDE.md). The
manual escape hatch is the filesystem itself — notes are plain markdown.

```
src/notes_mcp/
  notes_store.py # NEW: dated-folder entry writing, listing, reading
  embeddings.py  # NEW: fastembed wrapper, cosine similarity, semantic search
  server.py      # tool surface: create_note, search, list_recent, read_note
```

## Storage (their structure)

```
~/.notes/                        # existing root; ~/.notesrc still honored
  2026-05-14-...-my-first-note.md   # legacy flat notes — left in place, searchable
  2026-07-04/
    14-30-52.md                  # note entry
    14-30-52.embedding           # companion vector
```

- New notes: dated folder `YYYY-MM-DD/`, filename `HH-MM-SS.md` (append `-2`
  on same-second collision). No slug — filenames are timestamps.
- Entry format: YAML frontmatter + markdown body:

  ```
  ---
  title: "2:30:52 PM - July 4, 2026"   # display only; AI may set a better one
  date: 2026-07-04T14:30:52
  category: user_context               # optional; one of the five below
  tags: []                             # optional
  ---

  Full note content...
  ```

- `category`: `feelings`, `project_notes`, `user_context`,
  `technical_insights`, `world_knowledge` (labels only).
- Companion `.embedding` JSON beside every note: `model` name + `vector`.
- Legacy flat notes are indexed by the same search (embeddings backfilled by
  self-healing); they are never modified.

## MCP Tools (complete surface — four tools)

All previous note tools (`show_note`, `append_note`, `replace_section`,
`insert_after_heading`, `tag_note`, `delete_note`, `list_notes`,
`count_notes`, `search_notes`) are REMOVED entirely, along with the CLI.
Editing and deletion are impossible by omission — the wall. Manual file
management happens directly on the filesystem.

### `create_note(content, category=None, title=None)`

Creates a new entry in today's dated folder, embeds it. Tool description
carries the update discipline: "To update existing knowledge, write a new
note containing the complete updated context — never a fragment."

### `search(query, limit=10)`

Semantic search over ALL notes (new-style and legacy). Returns per result:
path, date, title, category, similarity score, snippet. Description
instructs: results may include older notes on the same topic — newest
content wins; read dates carefully.

### `list_recent(days=7)`

Notes from the last `days` days, newest first (date from folder/filename;
legacy notes from filename timestamp).

### `read_note(path)`

Full markdown of one note by path (as returned by search/list_recent).
**Path guard:** refuses paths outside the notes folder.

## Behavior layer — user's global CLAUDE.md (deployment step)

Flows live in the user's global `~/.claude/CLAUDE.md` (not the repo's project
CLAUDE.md); the repo README documents the snippet:

**Save flow.** Gather content (follow-up question or fetch the linked
article) → pick category → `create_note` → offer to discuss/develop/extend,
contributing insights → on finish, `create_note` again with the full updated
context including the discussion summary.

**Recall flow.** `search` → `read_note` the relevant results, newest first,
newest content authoritative → offer the same engagement → on finish,
`create_note` with the complete updated context.

**Update discipline.** Never write partial updates; every new note on an
existing topic must stand alone as the current truth of that topic.

## Embeddings

- `fastembed` (ONNX, no PyTorch), model `all-MiniLM-L6-v2` (384-dim);
  one-time ~90 MB download on first use, then offline.
- Lazy initialization on first use; server startup stays instant.
- `embeddings.py`: `embed_text(text)` and `search(query, candidates)`;
  cosine similarity as a plain function.
- `.embedding` records the model name; missing/corrupt/mismatched embeddings
  are regenerated from the markdown on search (self-healing — also backfills
  all legacy notes on first search).

## Error Handling

Theme: never lose a note.

- Embedding failure: note still saves; backfilled on later search.
- Corrupt/missing `.embedding`: regenerate.
- Invalid `category`: save without category, mention it in the response.
- Same-second collision: `-2` suffix.
- `read_note` outside the notes folder: refusal message.

## Testing

- pytest, notes folder pointed at temp dirs.
- Unit: dated-folder + timestamp filename creation, collision suffix,
  frontmatter (title/date/category/tags), category validation fallback,
  recency listing across new-style and legacy files, path guard.
- Search: fake embedder (fixed vectors) for deterministic ranking, legacy
  backfill, model-mismatch regeneration.
- One optional integration test with real fastembed, marked slow/skippable.
- `test_core.py` is DELETED with `core.py`; the new suite fully replaces it.

## Dependencies

- `fastembed` added to `pyproject.toml`.

## Build Order (suggested)

1. `notes_store.py`: dated-folder entry writing + `create_note` +
   `list_recent` + `read_note` with path guard; new server tool surface;
   delete `core.py`, `cli.py`, `test_core.py`, and the console-script entry
2. `embeddings.py` + embedding-on-write + `search` + self-healing/backfill
3. README rewrite + global-CLAUDE.md snippet (save flow, recall flow, update
   discipline); deployment: `uv tool uninstall` old CLI, update user's
   CLAUDE.md Notes section
