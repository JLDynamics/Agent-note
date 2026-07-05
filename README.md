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