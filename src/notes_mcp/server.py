"""Notes MCP server — append-only AI-organized notes.

Four tools only. No tool modifies or deletes an existing file: updates are
new notes carrying the complete updated context; newest content wins.
"""
import json

from mcp.server.fastmcp import FastMCP

from notes_mcp import embeddings, notes_store

mcp = FastMCP("notes")

TOOL_NAMES = ("create_note", "search", "list_recent", "read_note")

# Category definitions used in the tool description so the AI can route content
# itself. Keep these in sync with notes_store.CATEGORIES (a test guards this).
_CATEGORY_HELP = {
    "feelings": "reflections, mood, emotional noticings, what you processed or felt",
    "project_notes": "current or future projects (this one, or anything else being built)",
    "user_context": "facts about the user (Jack): preferences, communication style, working patterns, life situation",
    "technical_insights": "coding and software learnings beyond a specific project",
    "world_knowledge": "general facts, domain knowledge, how systems work",
}

_CREATE_NOTE_DESCRIPTION = """Save a new note. Notes are append-only: to UPDATE existing
knowledge, create a new note containing the COMPLETE updated context (never just
the change) — the newest note on a topic wins.

Infer `category` and `title` from the content yourself and save in one step —
NEVER ask the user for a category or title. Only ask the user a follow-up when
the content itself is unclear or missing.

Categories (pick the single best fit):
""" + "\n".join(
    f"    - {name}: {desc}" for name, desc in _CATEGORY_HELP.items()
) + """

If a note genuinely spans several, pick the dominant one; when uncertain,
prefer leaving category unset rather than asking."""


@mcp.tool(description=_CREATE_NOTE_DESCRIPTION)
def create_note(content: str, category: str | None = None, title: str | None = None) -> str:
    """Save a new note (append-only). The full description rich categories and
    the infer-don't-ask instruction is attached via the decorator so it reaches
    the model reliably regardless of how the client renders docstrings."""
    path, warning = notes_store.create_entry(content, category=category, title=title)
    embeddings.try_embed_note(path)
    return json.dumps({"path": str(path), "warning": warning})


@mcp.tool()
def search(query: str, limit: int = 10, category: str | None = None) -> str:
    """Hybrid semantic + keyword search over ALL notes. Results may include
    older notes on the same topic — read dates carefully: the NEWEST content
    is authoritative, older results are history. Short notes include full
    text; truncated ones need read_note. Optional category filter."""
    results = embeddings.search(query, limit=limit, category=category)
    return json.dumps(results)


@mcp.tool()
def list_recent(days: int = 7, category: str | None = None) -> str:
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
    except (ValueError, OSError) as exc:
        return f"Refused or not found: {exc}"


if __name__ == "__main__":
    mcp.run()
