import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest

from notes_mcp import notes_store


@pytest.fixture
def notes_folder(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(notes_store, "get_notes_folder", lambda: folder)
    return folder


FIXED_NOW = datetime(2026, 7, 4, 14, 30, 52)


def test_create_entry_writes_dated_file(notes_folder):
    path, warning = notes_store.create_entry("Buy milk and eggs", now=FIXED_NOW)
    assert path == notes_folder / "2026-07-04" / "14-30-52.md"
    assert path.exists()
    assert warning is None
    meta, body = notes_store.parse_frontmatter(path.read_text())
    assert body.strip() == "Buy milk and eggs"
    assert meta["date"] == "2026-07-04T14:30:52"
    assert meta["title"] == "2:30:52 PM - July 4, 2026"


def test_create_entry_with_tags_and_title(notes_folder):
    path, warning = notes_store.create_entry(
        "I prefer simple explanations",
        tags=["User Context", "Communication Style", "user-context"],
        title="Preferred learning style", now=FIXED_NOW)
    meta, _ = notes_store.parse_frontmatter(path.read_text())
    assert json.loads(meta["tags"]) == [
        "user-context", "communication-style"
    ]
    assert notes_store.note_info(path)["tags"] == [
        "user-context", "communication-style"
    ]
    assert meta["title"] == "Preferred learning style"
    assert warning is None


def test_title_with_quotes_round_trips(notes_folder):
    title = 'A user said "keep the raw copy"'
    path, _ = notes_store.create_entry("content", title=title, now=FIXED_NOW)
    assert notes_store.note_info(path)["title"] == title


def test_create_entry_cleans_invalid_tags_but_saves_anyway(notes_folder):
    path, warning = notes_store.create_entry(
        "text", tags=["", None, "  MCP Server  "], now=FIXED_NOW
    )
    assert path.exists()
    assert notes_store.note_info(path)["tags"] == ["mcp-server"]
    assert "invalid tags" in warning


def test_create_entry_rejects_empty_content(notes_folder):
    with pytest.raises(ValueError, match="empty"):
        notes_store.create_entry("", now=FIXED_NOW)
    with pytest.raises(ValueError, match="empty"):
        notes_store.create_entry("   \n\t  ", now=FIXED_NOW)
    assert list(notes_folder.rglob("*.md")) == []


def test_iter_note_infos_skips_unreadable_files(notes_folder):
    good, _ = notes_store.create_entry("good note", now=FIXED_NOW)
    bad = notes_folder / "2026-07-04" / "00-00-00.md"
    bad.write_bytes(b"\xff\xfe not utf-8")
    infos = list(notes_store.iter_note_infos())
    assert [i["path"] for i in infos] == [str(good)]


def test_list_recent_and_list_tags_survive_bad_files(notes_folder, monkeypatch):
    notes_store.create_entry(
        "fresh", tags=["ok-tag"], now=FIXED_NOW
    )
    bad = notes_folder / "2026-07-04" / "00-00-01.md"
    bad.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(notes_store, "_now", lambda: datetime(2026, 7, 5, 9, 0, 0))
    recent = notes_store.list_recent(days=7)
    assert len(recent) == 1
    assert recent[0]["text"].strip() == "fresh"
    assert notes_store.list_tags() == [{"tag": "ok-tag", "count": 1}]


def test_normalize_tags_limits_deduplicates_and_cleans():
    values = ["MCP", "mcp", "Memory System", "python_code"] + [
        f"Tag {index}" for index in range(10)
    ]
    tags, warning = notes_store.normalize_tags(values)
    assert tags[:3] == ["mcp", "memory-system", "python-code"]
    assert len(tags) == notes_store.MAX_TAGS
    assert "first 8 unique tags" in warning


def test_create_entry_same_second_collision(notes_folder):
    p1, _ = notes_store.create_entry("first", now=FIXED_NOW)
    p2, _ = notes_store.create_entry("second", now=FIXED_NOW)
    p3, _ = notes_store.create_entry("third", now=FIXED_NOW)
    assert p1.name == "14-30-52.md"
    assert p2.name == "14-30-52-2.md"
    assert p3.name == "14-30-52-3.md"
    assert p1.read_text() != p2.read_text()


def test_create_entry_concurrent_writers_never_overwrite(notes_folder):
    def save(index):
        path, _ = notes_store.create_entry(f"entry {index}", now=FIXED_NOW)
        return path

    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(save, range(20)))

    assert len(set(paths)) == 20
    bodies = {
        notes_store.parse_frontmatter(path.read_text(encoding="utf-8"))[1].strip()
        for path in paths
    }
    assert bodies == {f"entry {index}" for index in range(20)}


def test_parse_frontmatter_no_frontmatter():
    meta, body = notes_store.parse_frontmatter("# Just a heading\n\ntext\n")
    assert meta == {}
    assert body.startswith("# Just a heading")


def test_get_notes_folder_respects_notesrc(tmp_path, monkeypatch):
    custom = tmp_path / "custom_notes"
    rc = tmp_path / ".notesrc"
    rc.write_text(json.dumps({"notes_folder": str(custom)}))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert notes_store.get_notes_folder() == custom
    assert custom.exists()


def test_parse_frontmatter_body_horizontal_rule_preserved(notes_folder):
    content = "Intro text\n\n---\n\nMore text after a horizontal rule"
    path, _ = notes_store.create_entry(content, now=FIXED_NOW)
    meta, body = notes_store.parse_frontmatter(path.read_text())
    assert "More text after a horizontal rule" in body
    assert "Intro text" in body
    assert meta["date"] == "2026-07-04T14:30:52"


def test_parse_frontmatter_leading_rule_is_not_frontmatter():
    text = "---\n\nJust a doc starting with a horizontal rule\n---\nmore\n"
    meta, body = notes_store.parse_frontmatter(text)
    assert meta == {}
    assert body == text  # nothing swallowed


def test_parse_frontmatter_unclosed_returns_everything():
    text = "---\ntitle: oops no closing delimiter\n"
    meta, body = notes_store.parse_frontmatter(text)
    assert meta == {}
    assert body == text


def _legacy_note(folder, name, text="# Old note\n\nlegacy content\n"):
    p = folder / name
    p.write_text(text)
    return p


def test_iter_note_paths_covers_legacy_and_dated(notes_folder):
    legacy = _legacy_note(notes_folder, "2026-05-14-205701-my-first-note.md")
    new, _ = notes_store.create_entry("new style", now=FIXED_NOW)
    paths = notes_store.iter_note_paths()
    assert legacy in paths and new in paths
    assert all(p.suffix == ".md" for p in paths)


def test_iter_note_paths_excludes_raw_markdown_and_symlink_escapes(
    notes_folder, tmp_path
):
    normal, _ = notes_store.create_entry("normal", now=FIXED_NOW)
    raw = notes_folder / ".raw" / "conversations" / "conv-test"
    raw.mkdir(parents=True)
    raw_markdown = raw / "source.md"
    raw_markdown.write_text("raw source")
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    link = notes_folder / "linked.md"
    link.symlink_to(outside)

    assert notes_store.iter_note_paths() == [normal]


def test_note_date_new_style_and_legacy(notes_folder):
    new, _ = notes_store.create_entry("x", now=FIXED_NOW)
    assert notes_store.note_date(new) == FIXED_NOW
    legacy = _legacy_note(notes_folder, "2026-05-14-205701-my-first-note.md")
    assert notes_store.note_date(legacy) == datetime(2026, 5, 14, 20, 57, 1)


def test_note_date_unparseable_falls_back_to_mtime(notes_folder):
    weird = _legacy_note(notes_folder, "20260513_225818_my_first_note.md")
    got = notes_store.note_date(weird)
    assert got == datetime.fromtimestamp(weird.stat().st_mtime)


def test_list_recent_filters_by_days_and_tags(notes_folder, monkeypatch):
    old_now = datetime(2026, 6, 1, 10, 0, 0)
    notes_store.create_entry("old note", now=old_now)
    notes_store.create_entry("fresh plain", now=FIXED_NOW)
    notes_store.create_entry(
        "fresh feeling",
        tags=["feelings", "personal-reflection"],
        now=datetime(2026, 7, 4, 15, 0, 0),
    )
    monkeypatch.setattr(notes_store, "_now", lambda: datetime(2026, 7, 5, 9, 0, 0))

    recent = notes_store.list_recent(days=7)
    texts = [r["text"].strip() for r in recent]
    assert texts == ["fresh feeling", "fresh plain"]  # newest first, no old note

    only_feelings = notes_store.list_recent(days=7, tags=["Feelings"])
    assert len(only_feelings) == 1
    assert only_feelings[0]["tags"] == ["feelings", "personal-reflection"]


def test_list_tags_counts_usage_and_reads_legacy_category(notes_folder):
    notes_store.create_entry("one", tags=["MCP", "memory"], now=FIXED_NOW)
    notes_store.create_entry(
        "two", tags=["mcp", "python"],
        now=datetime(2026, 7, 4, 15, 0, 0),
    )
    legacy = notes_folder / "2026-05-14-205701-old.md"
    legacy.write_text(
        "---\ntitle: Old\ndate: 2026-05-14T20:57:01\n"
        "category: technical_insights\n---\n\nlegacy\n"
    )

    assert notes_store.note_info(legacy)["tags"] == ["technical-insights"]
    assert notes_store.list_tags() == [
        {"tag": "mcp", "count": 2},
        {"tag": "memory", "count": 1},
        {"tag": "python", "count": 1},
        {"tag": "technical-insights", "count": 1},
    ]


def test_read_note_returns_content(notes_folder):
    path, _ = notes_store.create_entry("readable", now=FIXED_NOW)
    assert "readable" in notes_store.read_note(str(path))


def test_read_note_refuses_outside_paths(notes_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private key")
    with pytest.raises(ValueError):
        notes_store.read_note(str(secret))
    with pytest.raises(ValueError):
        notes_store.read_note(str(notes_folder / ".." / "secret.txt"))


def test_read_note_refuses_raw_conversation_and_embedding_files(notes_folder):
    raw = notes_folder / ".raw" / "conversations" / "conv-test"
    raw.mkdir(parents=True)
    transcript = raw / "conversation.txt"
    transcript.write_text("large raw conversation")
    raw_markdown = raw / "conversation.md"
    raw_markdown.write_text("raw markdown conversation")
    embedding = notes_folder / "note.embedding"
    embedding.write_text("{}")

    with pytest.raises(ValueError, match="raw source data"):
        notes_store.read_note(str(transcript))
    with pytest.raises(ValueError, match="raw source data"):
        notes_store.read_note(str(raw_markdown))
    with pytest.raises(ValueError, match="not a Markdown note"):
        notes_store.read_note(str(embedding))


def test_read_note_refuses_symlink_escape(notes_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    link = notes_folder / "sneaky.md"
    link.symlink_to(secret)
    with pytest.raises(ValueError):
        notes_store.read_note(str(link))


def test_list_recent_truncates_long_notes(notes_folder, monkeypatch):
    notes_store.create_entry("short one", now=FIXED_NOW)
    notes_store.create_entry("food " + "x" * 2000, now=datetime(2026, 7, 4, 15, 0, 0))
    monkeypatch.setattr(notes_store, "_now", lambda: datetime(2026, 7, 5, 9, 0, 0))
    recent = notes_store.list_recent(days=7)
    long_note, short_note = recent[0], recent[1]
    assert long_note["truncated"] is True
    assert len(long_note["text"]) <= 300
    assert short_note["truncated"] is False
    assert short_note["text"].strip() == "short one"


def test_notesrc_invalid_json_gives_clear_error(tmp_path, monkeypatch):
    (tmp_path / ".notesrc").write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(ValueError, match="notesrc"):
        notes_store.get_notes_folder()


@pytest.mark.parametrize(
    "config, message",
    [
        ("[]", "JSON object"),
        ('{"notes_folder": 123}', "non-empty path string"),
        ('{"notes_folder": ""}', "non-empty path string"),
    ],
)
def test_notesrc_rejects_invalid_shapes(tmp_path, monkeypatch, config, message):
    (tmp_path / ".notesrc").write_text(config, encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(ValueError, match=message):
        notes_store.get_notes_folder()
