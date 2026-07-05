# Notes MCP Server

A simple markdown notes app exposed as an [MCP](https://modelcontextprotocol.io) server. Notes are stored as `.md` files in `~/.notes/`, named `{timestamp}-{slug}.md`.

## Project layout

```
src/notes_mcp/     # installable package
  core.py          # note storage and operations
  server.py        # MCP server
  cli.py           # terminal commands
tests/             # pytest suite
```

## Install

```bash
pip install -e .
# or with dev dependencies:
uv sync --group dev
```

## Run MCP server

```bash
python -m notes_mcp.server
```

Or via the MCP CLI:

```bash
mcp run -m notes_mcp.server
```

## Tools

The server exposes these MCP tools:

| Tool | Description |
|---|---|
| `list_notes` | List all note filenames, newest first |
| `show_note` | Show full contents of a note by title |
| `search_notes` | Search note contents for text |
| `count_notes` | Return total number of notes |
| `create_note` | Create a new markdown note with title and optional content |
| `delete_note` | Delete a note by title |
| `tag_note` | Add a tag to a note's frontmatter |
| `append_note` | Append text to the end of a note |
| `replace_section` | Replace the first match of a text block in a note |
| `insert_after_heading` | Insert content right after a specific heading |

## Command-line tool (CLI)

Install globally with:

```bash
uv tool install .
```

Then run commands from any folder:

```bash
notes create "buy milk"
notes list
notes show "buy milk"
notes search "milk"
notes delete "buy milk"
notes --help          # see all commands
```

## Configuration

By default, notes are saved to `~/.notes`.

To use a different folder, create a file at `~/.notesrc`:

```json
{
  "notes_folder": "~/Documents/MyNotes"
}
```

(See `.notesrc.example` in this repo for a sample.)

## Storage

Notes live in `~/.notes/` by default. Each note is a markdown file with optional YAML frontmatter for tags:

```markdown
---
tags: [idea, work]
---

# My Note

Content here.
```

## Tests

```bash
pytest
```