from mcp.server.fastmcp import FastMCP

from notes_mcp import core

mcp = FastMCP("notes")


@mcp.tool()
def list_notes() -> str:
    """List all note filenames, newest first."""
    return core.list_notes()


@mcp.tool()
def show_note(title: str) -> str:
    """Show the full contents of the note matching the given title."""
    return core.show_note(title)


@mcp.tool()
def search_notes(query: str) -> str:
    """Search note contents for text; returns names of matching notes."""
    return core.search_notes(query)


@mcp.tool()
def count_notes() -> str:
    """Return the total number of notes."""
    return core.count_notes()


@mcp.tool()
def create_note(title: str, content: str = "") -> str:
    """Create a new markdown note with the given title and optional content.
    Returns the path to the created note."""
    return core.create_note(title, content)


@mcp.tool()
def delete_note(title: str) -> str:
    """Delete the note matching the given title."""
    return core.delete_note(title)


@mcp.tool()
def tag_note(title: str, tag: str) -> str:
    """Add a tag to the note's frontmatter."""
    return core.tag_note(title, tag)


@mcp.tool()
def append_note(title: str, content: str) -> str:
    """Append text to the end of an existing note."""
    return core.append_note(title, content)


@mcp.tool()
def replace_section(title: str, old_text: str, new_text: str) -> str:
    """Replace a specific block of text in a note. Only the first match is replaced.
    Use show_note first to read the current content, then identify the exact text to replace."""
    return core.replace_section(title, old_text, new_text)


@mcp.tool()
def insert_after_heading(title: str, heading: str, content: str) -> str:
    """Insert content immediately after a specific heading in a note.
    The heading should match the text after the # markers (e.g. 'Ideas' for '## Ideas')."""
    return core.insert_after_heading(title, heading, content)


if __name__ == "__main__":
    mcp.run()