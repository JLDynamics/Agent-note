# AI-Organized Notes for notes-mcp — Design

**Date:** 2026-07-04
**Status:** Approved pending final review
**Inspired by:** category frontmatter and semantic search from
[private-journal-mcp](https://github.com/obra/private-journal-mcp). Its
memory/journal layer and dual storage scopes are deliberately NOT adopted —
this is a private note-taking system for the user, with the AI as organizer.

## Goal

Upgrade notes-mcp so the AI can act as the user's note librarian:

- **Save flow:** user asks to save anything (idea, learning, text, linked
  article). The AI gathers the content, picks a category, saves the note with
  frontmatter, then offers to discuss and develop the idea; the discussion
  summary is appended to the same note.
- **Recall flow:** user asks about something saved. The AI finds it via
  semantic search, reads it, offers the same discuss/develop engagement, and
  appends the new discussion's summary to the note.

Notes are living documents that accumulate thinking over time — via
**append-only versioning**: files are never modified or deleted through MCP;
every change creates a new version file, and the newest version of a note is
authoritative ("current knowledge wins").

## Scope

**In:** AI classification with category frontmatter, semantic search over
notes, recency listing, existing editing tools retained, behavior workflows
via the user's global CLAUDE.md.

**Out (explicitly):** the journal/memories layer (`process_thoughts`, memory
folders, AI self-journaling) and dual storage scopes — all notes live in the
single user notes folder, as today. Also out: vector databases, cloud
embedding APIs. (Their append-only, never-modify file discipline IS adopted —
but applied to the user's notes as versioning, not to an AI journal.)

## Architecture

```
src/notes_mcp/
  core.py        # note storage/editing — UNCHANGED
  embeddings.py  # NEW: fastembed wrapper, cosine similarity, semantic search
  server.py      # note tools + category support + semantic search + list_recent
  cli.py         # unchanged
```

## Storage

```
~/.notes/                  # existing folder, existing format
  {timestamp}-{slug}.md
```

- No migration, no new folders. `~/.notesrc` (`notes_folder`) keeps working.
- **Versioning:** a note's identity is its slug. Files sharing a slug are
  versions of the same note; the one with the newest timestamp is the
  current version. The existing `_find_note` (newest-first match) already
  resolves titles to the current version. Older files are never touched.
- Note frontmatter: existing `tags` plus new `category` — one of `feelings`,
  `project_notes`, `user_context`, `technical_insights`, `world_knowledge` —
  chosen by the AI when saving (optional: a note may have no category).
  Category is a label only; it does not affect where the note is stored.
- Companion `.embedding` file beside every note: JSON with `model` name and
  `vector`.

## MCP Tools

### Note tools (copy-on-write semantics)

**The wall (enforced by omission, like private-journal-mcp):** no MCP tool
modifies or deletes an existing file. `delete_note` is REMOVED from the MCP
server (it stays in `core.py`/CLI as the user's manual escape hatch).

- `create_note` gains an optional `category` argument, written into
  frontmatter. Creating a title whose slug already exists creates a new
  version of that note (same slug, new timestamp) — this is the intended way
  to supersede.
- Editing tools (`append_note`, `replace_section`, `insert_after_heading`,
  `tag_note`) keep their names and interface, but are reimplemented
  copy-on-write in the server layer: read the current version, apply the
  change, save the result as a NEW version file. The original is untouched.
- `show_note` returns the current (newest) version — existing behavior.
- `list_notes` / `count_notes` report current versions (dedupe by slug),
  with a version count per note.
- After any version write, embed the new file. Old versions keep their
  embeddings (they remain searchable as history).
- `search_notes` (keyword) is REMOVED from the MCP server, replaced by
  `search` below. The function stays in `core.py` for the CLI.

### `search(query, limit=10)` — NEW

Semantic search over ALL files — current and historical versions. Embeds the
query, ranks all `.embedding` vectors by cosine similarity, returns top
`limit`: filename, date, title, category, similarity score, snippet, and a
version marker: `current` or `older version (superseded YYYY-MM-DD)`.
**Current knowledge wins:** the tool description instructs the AI to treat
the current version as authoritative and older versions as history/context.

### `list_recent(days=7)` — NEW

Notes from the last `days` days, newest first, with date/title/category.
(Derived from the timestamp in the filename.)

## Behavior layer — user's global CLAUDE.md (deployment step)

The server provides tools; the flows are driven by a standing section in the
user's global `~/.claude/CLAUDE.md` (NOT the repo's project CLAUDE.md — they
must apply in every session). The repo README documents the recommended
snippet. Two flows, mirroring the user's diagrams:

**Save flow.** On any save request: gather content (ask a follow-up or fetch
the linked article if needed) → pick category → `create_note` with category →
read the note back and offer to discuss, develop, or extend the idea,
contributing insights → when the discussion finishes, append a summary of the
conversation to the same note.

**Recall flow.** On a question about saved content: `search` → read the
matching note(s) via `show_note` → offer the same discuss/develop/extend
engagement → when finished, append the new discussion's summary to the same
note.

## Embeddings

- Library: `fastembed` (ONNX, no PyTorch), model `all-MiniLM-L6-v2` (384-dim).
  One-time ~90 MB model download on first use, then fully offline.
- Lazy initialization: the model loads on the first tool call that needs it;
  server startup stays instant.
- `embeddings.py` exposes `embed_text(text) -> list[float]` and
  `search(query, candidates) -> ranked results`. Cosine similarity as a plain
  function (no numpy at this scale).
- Every `.embedding` records the model name. On search, a missing, corrupt, or
  model-mismatched embedding is regenerated from the note markdown
  (self-healing). This also backfills notes created via the CLI or edited by
  hand, including the user's existing notes on first search.

## Error Handling

Theme: never lose a note.

- Embedding failure (e.g. offline first run): the note still saves; the
  embedding is backfilled by self-healing on a later search.
- Corrupt/missing `.embedding`: regenerate from the note.
- Invalid `category` value: save anyway without category, mention it in the
  response (never lose content over metadata).
- Two versions in the same second (same slug, same timestamp): append `-2`
  to the filename rather than overwrite.

## Testing

- pytest, existing pattern: notes folder pointed at a temp dir (as
  `test_core.py` already does).
- Unit: category frontmatter written on create, category coexists with tags,
  recency filter, copy-on-write editing (original file byte-identical after
  an append/replace/tag; new version contains the change), current-version
  resolution by slug, list/count dedupe with version counts, same-second
  version collision suffix, new version embedded on write.
- Search: fake embedder (stub with fixed vectors) for fast, offline,
  deterministic ranking tests, including model-mismatch regeneration and
  backfill of embedding-less notes.
- One optional integration test with real fastembed, marked slow/skippable.
- Existing `test_core.py` suite must keep passing unchanged.

## Dependencies

- `fastembed` added to `pyproject.toml`. Acceptable for CLI installs for now;
  revisit as an optional extra if the package is published.

## Build Order (suggested)

1. `category` frontmatter on create + `list_recent`
2. Copy-on-write versioning: reimplement editing tools as new-version writes,
   current-version resolution, list/count dedupe, remove `delete_note` and
   `search_notes` from the server
3. `embeddings.py` + embedding-on-write + `search` with version markers +
   self-healing
4. README: recommended global-CLAUDE.md snippet (save flow + recall flow)
