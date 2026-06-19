import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path


def create_note(title, content=""):
    folder = Path.home() / ".notes"
    folder.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    slug = title.lower().replace(" ", "-")
    filename = f"{timestamp}-{slug}.md"
    path = folder / filename

    body = f"# {title}\n\n{content}\n" if content else f"# {title}\n\n"
    path.write_text(body)
    print(f"Created: {path}")


def _find_note(title):
    folder = Path.home() / ".notes"
    notes = sorted(folder.glob("*.md"), reverse=True)
    slug = title.lower().replace(" ", "-")
    for note in notes:
        if slug in note.name.lower():
            return note
    return None


def append_note(title, content):
    note = _find_note(title)
    if not note:
        print(f"No note found with title: {title}")
        return
    current = note.read_text()
    if not current.endswith("\n"):
        current += "\n"
    note.write_text(current + content + "\n")
    print(f"Appended to: {note.name}")


def replace_section(title, old_text, new_text):
    note = _find_note(title)
    if not note:
        print(f"No note found with title: {title}")
        return f"No note found with title: {title}"
    content = note.read_text()
    if old_text not in content:
        return f"Text not found in note: {title}"
    new_content = content.replace(old_text, new_text, 1)
    note.write_text(new_content)
    print(f"Replaced section in: {note.name}")
    return f"Replaced section in: {note.name}"


def insert_after_heading(title, heading, content):
    note = _find_note(title)
    if not note:
        print(f"No note found with title: {title}")
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
    print(f"Inserted under '{heading}' in: {note.name}")
    return f"Inserted under '{heading}' in: {note.name}"


def list_notes():
    folder = Path.home() / ".notes"
    notes = sorted(folder.glob("*.md"), reverse=True)

    if not notes:
        return "No notes yet."
    return "\n".join(note.name for note in notes)


def show_note(title):
    folder = Path.home() / ".notes"
    notes = sorted(folder.glob("*.md"), reverse=True)
    slug = title.lower().replace(" ", "-")

    for note in notes:
        if slug in note.name:
            return note.read_text()
    return f"No note found with title: {title}"


def delete_note(title):
    folder = Path.home() / ".notes"
    notes = sorted(folder.glob("*.md"), reverse=True)
    slug = title.lower().replace(" ", "-")

    for note in notes:
        if slug in note.name:
            note.unlink()
            print(f"Deleted: {note}")
            return

    print(f"No note found with title: {title}")


def count_notes():
    folder = Path.home() / ".notes"
    notes = sorted(folder.glob("*.md"), reverse=True)
    return f"Total notes: {len(notes)}"


def search_notes(query):
    folder = Path.home() / ".notes"
    notes = sorted(folder.glob("*.md"), reverse=True)
    matches = [note.name for note in notes if query.lower() in note.read_text().lower()]
    if not matches:
        return f"No notes found containing: {query}"
    return "\n".join(matches)


def edit_note(title):
    folder = Path.home() / ".notes"
    notes = sorted(folder.glob("*.md"), reverse=True)
    slug = title.lower().replace(" ", "-")

    for note in notes:
        if slug in note.name.lower():
            editor = os.environ.get("EDITOR", "nano")
            subprocess.run([editor, str(note)])
            return
    print(f"No note found with title: {title}")


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
    folder = Path.home() / ".notes"
    notes = sorted(folder.glob("*.md"), reverse=True)
    slug = title.lower().replace(" ", "-")
    tag = tag.lstrip("#").strip()

    for note in notes:
        if slug in note.name.lower():
            content = note.read_text()
            if content.startswith("---"):
                end = content.find("\n---", 3)
                if end == -1:
                    new_content = _make_frontmatter([tag]) + content
                else:
                    fm_block = content[:end]
                    body = content[end + 4:]
                    # fm_block is everything up to (but not including) the closing ---
                    existing = _extract_tags(fm_block)
                    if tag and tag not in existing:
                        existing.append(tag)
                    # Keep all original frontmatter lines except any old tags lines
                    fm_lines = [line for line in fm_block.splitlines() if not line.strip().lower().startswith("tags:")]
                    if existing:
                        fm_lines.append("tags: [" + ", ".join(existing) + "]")
                    new_fm = "\n".join(fm_lines) + "\n---\n\n"
                    new_content = new_fm + body.lstrip("\n")
            else:
                new_fm = _make_frontmatter([tag])
                new_content = new_fm + content
            note.write_text(new_content)
            print(f"Tagged: {note.name}")
            return

    print(f"No note found with title: {title}")


def main():
    parser = argparse.ArgumentParser(prog="notes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("title", nargs="+")

    subparsers.add_parser("list")

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("title", nargs="+")

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("title", nargs="+")

    subparsers.add_parser("count")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query", nargs="+")

    edit_parser = subparsers.add_parser("edit")
    edit_parser.add_argument("title", nargs="+")

    tag_parser = subparsers.add_parser("tag")
    tag_parser.add_argument("title", nargs="+")
    tag_parser.add_argument("tag")

    args = parser.parse_args()

    if args.command == "new":
        create_note(" ".join(args.title))
    elif args.command == "list":
        print(list_notes())
    elif args.command == "show":
        print(show_note(" ".join(args.title)))
    elif args.command == "delete":
        delete_note(" ".join(args.title))
    elif args.command == "count":
        print(count_notes())
    elif args.command == "search":
        print(search_notes(" ".join(args.query)))
    elif args.command == "edit":
        edit_note(" ".join(args.title))
    elif args.command == "tag":
        tag_note(" ".join(args.title), args.tag)


if __name__ == "__main__":
    main()
