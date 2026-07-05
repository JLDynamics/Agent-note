"""Append-only note storage: dated folders, YAML-ish frontmatter."""
import json
from datetime import datetime
from pathlib import Path

CATEGORIES = frozenset(
    ["feelings", "project_notes", "user_context", "technical_insights", "world_knowledge"]
)


def get_notes_folder():
    """Notes root: ~/.notes, or "notes_folder" from ~/.notesrc if present."""
    config_file = Path.home() / ".notesrc"
    default_folder = Path.home() / ".notes"
    if config_file.exists():
        config = json.loads(config_file.read_text())
        folder = Path(config.get("notes_folder", default_folder)).expanduser()
    else:
        folder = default_folder
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def parse_frontmatter(text):
    """Split a note into (meta dict, body). Tolerates missing frontmatter."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"')
    body = text[end + 4:].lstrip("\n")
    return meta, body


def _default_title(now):
    return now.strftime("%-I:%M:%S %p - %B %-d, %Y")


def create_entry(content, category=None, title=None, now=None):
    """Create a new note file in today's dated folder. Never overwrites.

    Returns (path, warning): warning is set when an invalid category was
    dropped (the note still saves — never lose content over metadata)."""
    now = now or datetime.now()
    folder = get_notes_folder() / now.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)

    warning = None
    if category is not None and category not in CATEGORIES:
        warning = (
            f"Unknown category '{category}' — saved without category. "
            f"Valid: {', '.join(sorted(CATEGORIES))}"
        )
        category = None

    stem = now.strftime("%H-%M-%S")
    path = folder / f"{stem}.md"
    counter = 2
    while path.exists():
        path = folder / f"{stem}-{counter}.md"
        counter += 1

    lines = [
        "---",
        f'title: "{title or _default_title(now)}"',
        f"date: {now.strftime('%Y-%m-%dT%H:%M:%S')}",
    ]
    if category:
        lines.append(f"category: {category}")
    lines += ["---", "", content, ""]
    path.write_text("\n".join(lines))
    return path, warning
