import json
from datetime import datetime
from pathlib import Path


def get_notes_folder():
    """Figure out where notes live.

    If the user has a config file at ~/.notesrc with a "notes_folder" value,
    use that. Otherwise fall back to the default ~/.notes folder.
    """
    config_file = Path.home() / ".notesrc"
    default_folder = Path.home() / ".notes"

    if config_file.exists():
        config = json.loads(config_file.read_text())
        folder = Path(config.get("notes_folder", default_folder)).expanduser()
    else:
        folder = default_folder

    folder.mkdir(parents=True, exist_ok=True)
    return folder


def create_note(title, content=""):
    folder = get_notes_folder()

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    slug = title.lower().replace(" ", "-")
    filename = f"{timestamp}-{slug}.md"
    path = folder / filename

    body = f"# {title}\n\n{content}\n" if content else f"# {title}\n\n"
    path.write_text(body)
    return f"Created: {path}"


def _find_note(title):
    folder = get_notes_folder()
    notes = sorted(folder.glob("*.md"), reverse=True)
    slug = title.lower().replace(" ", "-")
    for note in notes:
        if slug in note.name.lower():
            return note
    return None


def append_note(title, content):
    note = _find_note(title)
    if not note:
        return f"No note found with title: {title}"
    current = note.read_text()
    if not current.endswith("\n"):
        current += "\n"
    note.write_text(current + content + "\n")
    return f"Appended to: {note.name}"


def replace_section(title, old_text, new_text):
    note = _find_note(title)
    if not note:
        return f"No note found with title: {title}"
    content = note.read_text()
    if old_text not in content:
        return f"Text not found in note: {title}"
    new_content = content.replace(old_text, new_text, 1)
    note.write_text(new_content)
    return f"Replaced section in: {note.name}"


def insert_after_heading(title, heading, content):
    note = _find_note(title)
    if not note:
        return f"No note found with title: {title}"
    file_content = note.read_text()
    lines = file_content.splitlines(keepends=True)
    target = heading.strip().lstrip("#").strip()
    inserted = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            if heading_text.lower() == target.lower():
                lines.insert(i + 1, content + "\n")
                inserted = True
                break

    if not inserted:
        return f"Heading '{heading}' not found in note: {title}"

    note.write_text("".join(lines))
    return f"Inserted under '{heading}' in: {note.name}"


def list_notes():
    folder = get_notes_folder()
    notes = sorted(folder.glob("*.md"), reverse=True)

    if not notes:
        return "No notes yet."
    return "\n".join(note.name for note in notes)


def show_note(title):
    note = _find_note(title)
    if not note:
        return f"No note found with title: {title}"
    return note.read_text()


def delete_note(title):
    note = _find_note(title)
    if not note:
        return f"No note found with title: {title}"
    note.unlink()
    return f"Deleted: {note}"


def count_notes():
    folder = get_notes_folder()
    notes = sorted(folder.glob("*.md"), reverse=True)
    return f"Total notes: {len(notes)}"


def search_notes(query):
    folder = get_notes_folder()
    notes = sorted(folder.glob("*.md"), reverse=True)
    matches = [note.name for note in notes if query.lower() in note.read_text().lower()]
    if not matches:
        return f"No notes found containing: {query}"
    return "\n".join(matches)


def _extract_tags(fm_text):
    tags = []
    lines = fm_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("tags:"):
            rest = line[5:].strip()
            if rest.startswith("[") and rest.endswith("]"):
                inner = rest.strip("[] ,")
                if inner:
                    tags = [t.strip() for t in inner.split(",") if t.strip()]
            else:
                i += 1
                while i < len(lines):
                    current = lines[i].strip()
                    if current.startswith("- "):
                        t = current[2:].strip()
                        if t:
                            tags.append(t)
                    elif current and not current.startswith("#"):
                        break
                    i += 1
            break
        i += 1
    return tags


def _make_frontmatter(tags):
    if not tags:
        return ""
    return "---\ntags: [" + ", ".join(tags) + "]\n---\n\n"


def tag_note(title, tag):
    note = _find_note(title)
    if not note:
        return f"No note found with title: {title}"
    tag = tag.lstrip("#").strip()

    content = note.read_text()
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end == -1:
            new_content = _make_frontmatter([tag]) + content
        else:
            fm_block = content[:end]
            body = content[end + 4:]
            existing = _extract_tags(fm_block)
            if tag and tag not in existing:
                existing.append(tag)
            fm_lines = [line for line in fm_block.splitlines() if not line.strip().lower().startswith("tags:")]
            if existing:
                fm_lines.append("tags: [" + ", ".join(existing) + "]")
            new_fm = "\n".join(fm_lines) + "\n---\n\n"
            new_content = new_fm + body.lstrip("\n")
    else:
        new_fm = _make_frontmatter([tag])
        new_content = new_fm + content
    note.write_text(new_content)
    return f"Tagged: {note.name}"