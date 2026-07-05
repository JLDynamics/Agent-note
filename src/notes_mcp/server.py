"""Notes MCP server — append-only AI-organized notes.

Four tools only. No tool modifies or deletes an existing file: updates are
new notes carrying the complete updated context; newest content wins.
"""
import json

from mcp.server.fastmcp import FastMCP

from notes_mcp import embeddings, notes_store

mcp = FastMCP("notes")

TOOL_NAMES = ("create_note", "search", "list_recent", "read_note")

_CATEGORIES_DOC = ", ".join(sorted(notes_store.CATEGORIES))


@mcp.tool()
def create_note(content: str, category: str = None, title: str = None) -> str:
    """Save a new note. Notes are append-only: to UPDATE existing knowledge,
    create a new note containing the COMPLETE updated context (never just the
    change) — the newest note on a topic wins. Optional category, one of:
    feelings, project_notes, user_context, technical_insights, world_knowledge."""
    path, warning = notes_store.create_entry(content, category=category, title=title)
    embeddings.try_embed_note(path)
    return json.dumps({"path": str(path), "warning": warning})


@mcp.tool()
def search(query: str, limit: int = 10, category: str = None) -> str:
    """Hybrid semantic + keyword search over ALL notes. Results may include
    older notes on the same topic — read dates carefully: the NEWEST content
    is authoritative, older results are history. Short notes include full
    text; truncated ones need read_note. Optional category filter."""
    results = embeddings.search(query, limit=limit, category=category)
    return json.dumps(results)


@mcp.tool()
def list_recent(days: int = 7, category: str = None) -> str:
    """List notes from the last N days, newest first. Optional category
    filter (one of: feelings, project_notes, user_context,
    technical_insights, world_knowledge)."""
    return json.dumps(notes_store.list_recent(days=days, category=category))


@mcp.tool()
def read_note(path: str) -> str:
    """Read the full markdown of one note, by a path returned from search or
    list_recent. Only paths inside the notes folder are allowed."""
    try:
        return notes_store.read_note(path)
    except (ValueError, FileNotFoundError) as exc:
        return f"Refused or not found: {exc}"


if __name__ == "__main__":
    mcp.run()
