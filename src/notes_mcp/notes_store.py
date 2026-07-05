"""Append-only note storage: dated folders, YAML-ish frontmatter."""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

CATEGORIES = frozenset(
    ["feelings", "project_notes", "user_context", "technical_insights", "world_knowledge"]
)

# Notes longer than SNIPPET_LIMIT are returned as SNIPPET_LENGTH-char snippets
# (single source of truth — embeddings.search uses these too).
SNIPPET_LIMIT = 1500
SNIPPET_LENGTH = 300


def get_notes_folder():
    """Notes root: ~/.notes, or "notes_folder" from ~/.notesrc if present."""
    config_file = Path.home() / ".notesrc"
    default_folder = Path.home() / ".notes"
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"~/.notesrc contains invalid JSON ({exc}). "
                "Fix or delete the file — notes cannot be saved until then."
            ) from exc
        folder = Path(config.get("notes_folder", default_folder)).expanduser()
    else:
        folder = default_folder
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def parse_frontmatter(text):
    """Split a note into (meta dict, body). Tolerates missing frontmatter.

    Conservative on purpose: if the leading block doesn't look like real
    frontmatter (every line `key: value` until a closing ---), the whole
    text is returned as body — never silently drop content."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[i + 1:]).lstrip("\n")
            return meta, body
        if ":" not in line:
            return {}, text
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return {}, text


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
    path.write_text("\n".join(lines), encoding="utf-8")
    return path, warning


_LEGACY_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})")
_NEW_STEM = re.compile(r"^(\d{2})-(\d{2})-(\d{2})(?:-\d+)?$")
_DAY_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now():
    return datetime.now()


def iter_note_paths():
    return sorted(get_notes_folder().rglob("*.md"))


def note_date(path):
    """Best-effort creation time: dated-folder name, legacy filename, or mtime."""
    stem_match = _NEW_STEM.match(path.stem)
    if stem_match and _DAY_DIR.match(path.parent.name):
        h, m, s = (int(g) for g in stem_match.groups())
        y, mo, d = (int(x) for x in path.parent.name.split("-"))
        return datetime(y, mo, d, h, m, s)
    legacy = _LEGACY_DATE.match(path.name)
    if legacy:
        y, mo, d, h, m, s = (int(g) for g in legacy.groups())
        return datetime(y, mo, d, h, m, s)
    return datetime.fromtimestamp(path.stat().st_mtime)


def note_info(path):
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "date": note_date(path).isoformat(),
        "title": meta.get("title", path.stem),
        "category": meta.get("category"),
        "text": body,
    }


def list_recent(days=7, category=None):
    cutoff = _now() - timedelta(days=days)
    infos = [note_info(p) for p in iter_note_paths() if note_date(p) >= cutoff]
    if category:
        infos = [i for i in infos if i["category"] == category]
    for info in infos:
        info["truncated"] = len(info["text"]) > SNIPPET_LIMIT
        if info["truncated"]:
            info["text"] = info["text"][:SNIPPET_LENGTH]
    return sorted(infos, key=lambda i: i["date"], reverse=True)


def read_note(path_str):
    """Read one note by path. Refuses anything outside the notes root."""
    root = get_notes_folder().resolve()
    path = Path(path_str).expanduser().resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Refused: {path_str} is outside the notes folder")
    return path.read_text(encoding="utf-8")
