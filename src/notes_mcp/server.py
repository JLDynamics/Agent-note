"""Notes MCP server — append-only AI-organized notes.

No tool modifies or deletes an existing note: updates are new notes carrying
the complete updated context; newest content wins. Conversation imports keep a
raw source copy that the server does not rewrite, then the connected agent
derives ordinary notes through create_note.
"""
import json

from mcp.server.fastmcp import FastMCP

from notes_mcp import conversation_import, embeddings, notes_store

mcp = FastMCP("notes")

TOOL_NAMES = (
    "create_note",
    "import_conversation",
    "search",
    "list_recent",
    "list_tags",
    "read_note",
)

_CREATE_NOTE_DESCRIPTION = """Save a new note. Notes are append-only: to UPDATE existing
knowledge, create a new note containing the COMPLETE updated context (never just
the change) — the newest note on a topic wins.

Infer `title` and 3-8 short descriptive `tags` from the content yourself and
save in one step — NEVER ask the user for them. Reuse tags returned by
list_tags when they accurately fit; create new tags only when useful. Tags are
normalized automatically to lowercase words joined by hyphens. Prefer specific
topics such as `mcp`, `conversation-import`, or `python`; avoid generic tags
such as `note` or full sentence-like tags. Tags may be omitted when none add
useful meaning."""


@mcp.tool(description=_CREATE_NOTE_DESCRIPTION)
def create_note(
    content: str,
    tags: list[str] | None = None,
    title: str | None = None,
) -> str:
    """Save a new note with normalized tags (append-only)."""
    try:
        path, warning = notes_store.create_entry(content, tags=tags, title=title)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    embedded = embeddings.try_embed_note(path)
    info = notes_store.note_info(path)
    return json.dumps(
        {
            "path": str(path),
            "title": info["title"],
            "tags": info["tags"],
            "embedded": embedded,
            "warning": warning,
        }
    )


_IMPORT_CONVERSATION_DESCRIPTION = """Import a complete conversation transcript.
The raw transcript is saved unchanged and permanently under
.raw/conversations with a generated conversation ID and separate metadata.

Pass the complete transcript exactly as received. `original_date` is the date
of the original conversation when known; do not use the import date for it.

IMPORTANT: this tool only preserves the raw transcript. After it returns,
YOU (the connected agent) must immediately process the transcript already in
your context and call create_note once for each durable decision, fact, project,
action, preference, or reflection. Do not create notes for casual chatter.
Each note must stand alone, use 3-8 useful tags, and end with the exact source
block supplied in this tool's result. The block includes the original
conversation date when one was provided. Do not report the import as complete
until those create_note calls finish. Normal timestamps, embeddings, indexing,
and newest-note behavior come from create_note."""


@mcp.tool(description=_IMPORT_CONVERSATION_DESCRIPTION)
def import_conversation(
    content: str,
    original_date: str | None = None,
    title: str | None = None,
) -> str:
    """Preserve a conversation and hand note extraction back to the agent."""
    raw_record = conversation_import.save_raw_conversation(
        content,
        title=title,
        original_date=original_date,
    )
    conversation_id = raw_record["conversation_id"]
    source_lines = []
    if original_date:
        source_lines.append(f"Original conversation date: {original_date}")
    source_lines.append(f"Source conversation: {conversation_id}")
    source_block = "\n".join(source_lines)
    return json.dumps(
        {
            "status": "raw_saved",
            "agent_processing_required": True,
            "conversation_id": conversation_id,
            "transcript_path": raw_record["transcript_path"],
            "metadata_path": raw_record["metadata_path"],
            "source_block_for_notes": source_block,
            "next_action": (
                "Process the transcript supplied in your import_conversation "
                "call now. Extract only durable information, then call "
                "create_note once per standalone note with a title, 3-8 useful "
                f"tags, and this exact final source block:\n{source_block}"
            ),
        }
    )


@mcp.tool()
def search(query: str, limit: int = 10, tags: list[str] | None = None) -> str:
    """Hybrid semantic + keyword + tag search over ALL notes. Relevance stays
    primary; among closely relevant notes, the newest is returned first and is
    authoritative while older results are history. Short notes include full
    text; truncated ones need read_note. Optional tags filter requires every
    supplied tag to be present."""
    results = embeddings.search(query, limit=limit, tags=tags)
    return json.dumps(results)


@mcp.tool()
def list_recent(days: int = 7, tags: list[str] | None = None) -> str:
    """List notes from the last N days, newest first. Optional tags filter
    requires every supplied tag to be present."""
    return json.dumps(notes_store.list_recent(days=days, tags=tags))


@mcp.tool()
def list_tags() -> str:
    """List all normalized tags with note counts, most frequently used first.
    Use this before creating notes when you want to reuse established tags."""
    return json.dumps(notes_store.list_tags())


@mcp.tool()
def read_note(path: str) -> str:
    """Read the full markdown of one note, by a path returned from search or
    list_recent. Only paths inside the notes folder are allowed. Always returns
    JSON: {path, content} on success, {error} on failure."""
    try:
        content = notes_store.read_note(path)
    except (ValueError, OSError) as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"path": str(path), "content": content})


if __name__ == "__main__":
    mcp.run()
