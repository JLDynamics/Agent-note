"""Append-only note storage: dated folders, YAML-ish frontmatter."""
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

MAX_TAGS = 8
MAX_TAG_LENGTH = 40

# Notes longer than SNIPPET_LIMIT are returned as SNIPPET_LENGTH-char snippets
# (single source of truth — embeddings.search uses these too).
SNIPPET_LIMIT = 1500
SNIPPET_LENGTH = 300


def get_notes_folder():
    """Notes root: ~/.notesrc when configured, otherwise ~/.notes."""
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
        if not isinstance(config, dict):
            raise ValueError("~/.notesrc must contain a JSON object.")
        configured_folder = config.get("notes_folder")
        if configured_folder is None:
            folder = default_folder
        elif not isinstance(configured_folder, str) or not configured_folder.strip():
            raise ValueError("~/.notesrc notes_folder must be a non-empty path string.")
        else:
            folder = Path(configured_folder).expanduser()
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
        value = value.strip()
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = value.strip('"')
        meta[key.strip()] = value
    return {}, text


def _default_title(now):
    # %-I and %-d are convenient on POSIX but unsupported on Windows.
    hour = now.strftime("%I").lstrip("0") or "0"
    return f"{hour}:{now.strftime('%M:%S %p - %B')} {now.day}, {now.year}"


def normalize_tag(tag):
    """Normalize one tag to lowercase words separated by single hyphens."""
    if not isinstance(tag, str):
        return ""
    tag = tag.casefold().strip()
    # \w is Unicode-aware. Convert underscores and every other separator to a
    # hyphen, then collapse repeats so tags remain simple and predictable.
    tag = re.sub(r"[^\w]+", "-", tag, flags=re.UNICODE)
    tag = re.sub(r"[_-]+", "-", tag).strip("-")
    return tag[:MAX_TAG_LENGTH].rstrip("-")


def normalize_tags(tags):
    """Return (normalized tags, warning) without ever rejecting note content."""
    if tags is None:
        return [], None
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, (list, tuple)):
        return [], "Tags must be a list of text values — saved without tags."

    normalized = []
    saw_invalid = False
    saw_long = False
    for value in tags:
        if not isinstance(value, str) or not value.strip():
            saw_invalid = True
            continue
        clean = normalize_tag(value)
        if not clean:
            saw_invalid = True
            continue
        if len(value.strip()) > MAX_TAG_LENGTH:
            saw_long = True
        if clean not in normalized:
            normalized.append(clean)

    too_many = len(normalized) > MAX_TAGS
    normalized = normalized[:MAX_TAGS]
    warnings = []
    if saw_invalid:
        warnings.append("blank or invalid tags were removed")
    if saw_long:
        warnings.append(f"tags longer than {MAX_TAG_LENGTH} characters were shortened")
    if too_many:
        warnings.append(f"only the first {MAX_TAGS} unique tags were kept")
    warning = "; ".join(warnings).capitalize() + "." if warnings else None
    return normalized, warning


def _stored_tags(meta):
    """Read inline JSON tags and treat an old category as a legacy tag."""
    value = meta.get("tags")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in value.strip("[]").split(",")]
    elif isinstance(value, list):
        parsed = value
    else:
        parsed = []
    if meta.get("category"):
        parsed.append(meta["category"])
    tags, _ = normalize_tags(parsed)
    return tags


def create_entry(content, tags=None, title=None, now=None):
    """Create a new note file in today's dated folder. Never overwrites.

    Returns (path, warning). Invalid tag metadata is cleaned or dropped, but
    the note itself always saves so metadata can never cause content loss.
    Empty content is rejected — there is nothing durable to store."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("note content cannot be empty")

    now = now or datetime.now()
    folder = get_notes_folder() / now.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)

    normalized_tags, warning = normalize_tags(tags)

    note_title = str(title) if title is not None else _default_title(now)
    lines = [
        "---",
        f"title: {json.dumps(note_title, ensure_ascii=False)}",
        f"date: {now.strftime('%Y-%m-%dT%H:%M:%S')}",
    ]
    if normalized_tags:
        lines.append(f"tags: {json.dumps(normalized_tags, ensure_ascii=False)}")
    lines += ["---", "", content, ""]
    entry = "\n".join(lines)

    # Opening with mode "x" asks the OS to create the file only if it does
    # not already exist. The existence check and claim are one operation, so
    # simultaneous agents can never select and overwrite the same filename.
    stem = now.strftime("%H-%M-%S")
    counter = 1
    while True:
        suffix = "" if counter == 1 else f"-{counter}"
        path = folder / f"{stem}{suffix}.md"
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(entry)
            return path, warning
        except FileExistsError:
            counter += 1


_LEGACY_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})")
_NEW_STEM = re.compile(r"^(\d{2})-(\d{2})-(\d{2})(?:-\d+)?$")
_DAY_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now():
    return datetime.now()


def iter_note_paths():
    root = get_notes_folder().resolve()
    raw_root = (root / ".raw").resolve()
    paths = []
    for candidate in root.rglob("*.md"):
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            continue
        if resolved.is_relative_to(root) and not resolved.is_relative_to(raw_root):
            paths.append(candidate)
    return sorted(paths)


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
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"unreadable note: {path}") from exc
    meta, body = parse_frontmatter(raw)
    try:
        date = note_date(path).isoformat()
    except OSError as exc:
        raise ValueError(f"unreadable note: {path}") from exc
    return {
        "path": str(path),
        "date": date,
        "title": meta.get("title", path.stem),
        "tags": _stored_tags(meta),
        "text": body,
    }


def iter_note_infos():
    """Yield note_info dicts, skipping files that cannot be read or parsed."""
    for path in iter_note_paths():
        try:
            yield note_info(path)
        except (ValueError, OSError, UnicodeDecodeError):
            continue


def list_recent(days=7, tags=None):
    cutoff = _now() - timedelta(days=days)
    infos = []
    for path in iter_note_paths():
        try:
            if note_date(path) < cutoff:
                continue
            infos.append(note_info(path))
        except (ValueError, OSError, UnicodeDecodeError):
            continue
    required_tags, _ = normalize_tags(tags)
    if tags is not None:
        if not required_tags:
            return []
        required = set(required_tags)
        infos = [i for i in infos if required.issubset(i["tags"])]
    for info in infos:
        info["truncated"] = len(info["text"]) > SNIPPET_LIMIT
        if info["truncated"]:
            info["text"] = info["text"][:SNIPPET_LENGTH]
    return sorted(infos, key=lambda i: i["date"], reverse=True)


def list_tags():
    """Return normalized tags with usage counts, most common first."""
    counts = Counter(
        tag
        for info in iter_note_infos()
        for tag in info["tags"]
    )
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def read_note(path_str):
    """Read one Markdown note. Refuse raw data and paths outside the root."""
    root = get_notes_folder().resolve()
    path = Path(path_str).expanduser().resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Refused: {path_str} is outside the notes folder")
    if path.is_relative_to((root / ".raw").resolve()):
        raise ValueError(f"Refused: {path_str} is raw source data, not a note")
    if path.suffix.lower() != ".md":
        raise ValueError(f"Refused: {path_str} is not a Markdown note")
    return path.read_text(encoding="utf-8")
