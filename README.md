# Notes MCP Server

An append-only, AI-organized note system exposed as an
[MCP](https://modelcontextprotocol.io) server. The AI is the interface:
you talk, it files. Notes are markdown in dated folders under `~/.notes/`,
searchable by meaning via local embeddings (fastembed). Conversation imports
keep a local raw source copy that the server does not rewrite, then the
connected agent extracts durable information through the normal `create_note`
tool.

**Update model:** MCP tools never edit or delete notes. An update is a new note
carrying the complete updated context; the newest relevant note on a topic
wins. Old notes remain as searchable history. Files are not protected from
normal filesystem access: every note is plain markdown and can still be edited
or deleted outside the server.

## Layout

```
~/.notes/
  .raw/
    conversations/
      conv-20260720T093000-a1b2c3d4/
        conversation.txt # exact imported transcript
        metadata.json    # ID, dates, title, checksum
  2026-07-04/
    14-30-52.md          # one note
    14-30-52.embedding   # its chunk vectors (auto-regenerated if lost)
```

Configure a different root with:

- `~/.notesrc`: `{"notes_folder": "~/MyNotes"}`
- `~/.notes` when `.notesrc` is absent (default)

## Privacy and data handling

Agent-note is local-first, but it is not an encrypted vault:

- Notes, imported transcripts, metadata, and embedding companions are ordinary
  unencrypted files in the configured notes folder.
- Never commit, push, or otherwise publish that notes folder. It may contain
  private conversations and personal information.
- The embedding model downloads once on first use (about 90 MB). Embedding
  inference then runs locally through FastEmbed; note text and search queries
  are not sent to a hosted embedding API by this server.
- The connected MCP client receives tool inputs and results. Results can
  include note text, snippets, metadata, and absolute paths on the local
  machine. Review the privacy behavior of the client and model you connect.
- “Append-only” describes the MCP tools, not operating-system enforcement.
  Anyone or any process with access to the notes folder can change or remove
  its files. Imported transcripts include a checksum for provenance, but the
  server does not currently enforce that checksum.

## Tools

| Tool | Purpose |
|---|---|
| `create_note(content, tags?, title?)` | Save a new note with normalized tags (append-only). Returns `path`, `title`, `tags`, `embedded`, `warning` (or `error` if content is empty) |
| `import_conversation(content, original_date?, title?)` | Preserve a raw transcript and return a conversation ID plus instructions for the connected agent |
| `search(query, limit?, tags?)` | Hybrid semantic + keyword + tag search over title, tags, and body. Close matches are ordered newest-first; weak pure-semantic hits are dropped; optional tag filtering requires all supplied tags |
| `list_recent(days?, tags?)` | Recent notes, newest first, with optional tag filtering |
| `list_tags()` | Existing normalized tags with usage counts |
| `read_note(path)` | Full text of one note as JSON `{path, content}` (or `{error}`); paths from search/list |

## Tags

Notes can have zero to eight tags. The model normally supplies 3-8 descriptive
tags, and the storage layer makes them consistent:

- lowercase
- spaces and underscores changed to hyphens
- duplicate and blank tags removed
- maximum 40 characters per tag
- maximum eight unique tags per note

For example, `MCP`, `Memory System`, and `conversation_import` become `mcp`,
`memory-system`, and `conversation-import`. `list_tags` helps models reuse
established tags instead of creating slightly different names. Search uses
semantic meaning, words in the note, and tag matches together. Older notes
that still contain a category remain compatible: their old category is read
as a normalized legacy tag without rewriting the file.

## Current information and history

Search uses relevance first (title and tags are embedded alongside the body).
When several notes have close relevance scores (within 0.05), it orders those
notes newest-first. This makes a newer update win over an older version of the
same idea without allowing an unrelated recent note to outrank a clearly
relevant older note. Weak pure-semantic matches are omitted so agents are not
fed noise; keyword and tag hits still surface even when embedding scores are
low. Unreadable notes are skipped rather than failing the whole search. The
model still reads the dates: the newest relevant complete note is current, and
older versions are history.

Concurrent saves (e.g. multiple MCP clients writing at once) never collide:
note filenames are claimed with an atomic exclusive-create, so two notes in
the same second always get distinct files instead of one overwriting the
other. Embedding companions are also replaced atomically and carry a hash of
their note text. If a Markdown note is edited manually, its stale embedding is
detected and rebuilt automatically during the next search.

## Conversation import workflow

1. `import_conversation` saves the supplied transcript unchanged as
   `.raw/conversations/<conversation-id>/conversation.txt`. Metadata is kept
   separately, so the raw text is never rewritten.
2. The result returns the conversation ID and tells the connected agent to
   continue processing the transcript it already has in its chat context.
3. The agent extracts only durable decisions, knowledge, projects, actions,
   user context, and reflections. It ignores casual chatter and combines
   closely related details rather than creating duplicate notes.
4. The agent calls the existing `create_note` tool once for every extracted
   item, with a standalone title, complete content, 3-8 useful tags, and the
   source conversation ID. When supplied, the original conversation date is
   included in the same source block.
5. Each extracted item therefore receives the same dated Markdown filename,
   embedding, and search index as any manually created note.
6. Search handles recall normally. The importer contains no separate ranking,
   deduplication, database, or "newest wins" implementation.

The source conversation ID is appended to each derived note for traceability.
Raw transcripts are not indexed because they use `.txt`, not `.md`. Everything
below `.raw/` is excluded from note indexing and `read_note`, even if a raw
source happens to use a `.md` filename.

This design does not use MCP sampling, because many desktop clients do not
support that optional method. The same agent that called `import_conversation`
does the reasoning and follows with ordinary `create_note` calls. Embedding
generation remains local.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- An MCP client that can launch a local stdio server

The project is designed to be portable across macOS, Linux, and Windows.
Automated fast tests run on Linux; contributions that improve coverage on
other platforms are welcome.

## Install and run

```bash
git clone https://github.com/JLDynamics/Agent-note.git
cd Agent-note
uv sync

# Optional: download and initialize the embedding model now instead of
# waiting for the first note or search.
uv run python -c "from notes_mcp.embeddings import embed_text; embed_text('warm up')"

# Start the stdio MCP server directly.
uv run python -m notes_mcp.server
```

The first embedding operation downloads roughly 90 MB of model files. It can
therefore take longer and requires internet access. Later embedding and search
operations use the downloaded model locally.

For a client configured outside this repository, add an MCP server entry and
replace `<path-to-this-repo>` with the absolute path to your clone:

```json
{
  "mcpServers": {
    "notes": {
      "command": "uv",
      "args": ["run", "python", "-m", "notes_mcp.server"],
      "cwd": "<path-to-this-repo>"
    }
  }
}
```

The checked-in `.mcp.json` and `.codex/config.toml` use the same portable `uv`
command when a client opens this repository as its project directory. They do
not contain a user-specific home path.

## Basic usage

Once the client has connected, ask it to use the MCP tools. For example:

- “Save a note that the deployment checklist needs a database backup step.”
- “Search my notes for the deployment checklist.”
- “Show notes tagged `python` from the last seven days.”
- “Import this complete conversation and extract the durable decisions.”

The agent should call `create_note`, `search`, `list_recent`, `list_tags`,
`read_note`, or `import_conversation` as appropriate. Conversation import is a
two-part workflow: the tool first preserves the source transcript, then the
connected agent must create standalone durable notes from it.

Optional: initialize a **local or private-only** Git repository inside the
notes folder if you want file history. Never push that repository to a public
remote.

## Recommended global CLAUDE.md section

Replace any old "Notes CLI" section in `~/.claude/CLAUDE.md` with:

```markdown
## Notes (MCP)

I manage notes ONLY through the notes MCP tools (create_note,
import_conversation, search, list_recent, list_tags, read_note). Notes are
append-only and use tags instead of categories.

- **Save flow:** when I ask to save anything (idea, learning, text, or a
  linked article to summarize): gather the content (ask a follow-up or
  fetch the article), infer a title and 3-8 useful tags, then create_note.
  Reuse established tags from list_tags when they fit. Then read it back and
  offer to discuss/develop the idea with your own insights. When the
  discussion ends, create_note again with the COMPLETE updated context
  including a summary of the discussion.
- **Recall flow:** when I ask about something saved: search, read the
  closely relevant results newest-first — the newest relevant complete note on
  a topic is the truth, while older ones are history. Do not let a newer but
  unrelated note override a more relevant result. Offer the same
  discuss/develop engagement; on finish, create_note with the complete updated
  context.
- **Conversation import:** when I provide a complete exported conversation,
  call import_conversation once with the transcript exactly as received and
  its original date when known. After it returns, immediately extract only
  durable information from that transcript and call create_note once for each
  standalone note. Add the exact source block returned by the
  import tool to every derived note. This also preserves the original date when
  supplied. Do not stop after merely saving the raw
  transcript, and do not create duplicate notes from the same fact.
- **Update discipline:** never save fragments. Every new note on an
  existing topic must stand alone as the current, complete truth of it.
```

## Tests

```bash
uv run pytest            # fast suite (fake embeddings)
uv run pytest -m slow    # real-model integration test (~90 MB download)
```

The fast suite uses deterministic fake embeddings and does not download the
model. See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.

## License

Agent-note is available under the [MIT License](LICENSE).
