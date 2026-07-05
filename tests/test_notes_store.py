import json
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
    assert "title" in meta


def test_create_entry_with_category_and_title(notes_folder):
    path, warning = notes_store.create_entry(
        "I prefer simple explanations", category="user_context",
        title="Jack's learning style", now=FIXED_NOW)
    meta, _ = notes_store.parse_frontmatter(path.read_text())
    assert meta["category"] == "user_context"
    assert meta["title"] == "Jack's learning style"
    assert warning is None


def test_create_entry_invalid_category_saves_anyway(notes_folder):
    path, warning = notes_store.create_entry("text", category="nonsense", now=FIXED_NOW)
    assert path.exists()
    meta, _ = notes_store.parse_frontmatter(path.read_text())
    assert "category" not in meta
    assert "nonsense" in warning


def test_create_entry_same_second_collision(notes_folder):
    p1, _ = notes_store.create_entry("first", now=FIXED_NOW)
    p2, _ = notes_store.create_entry("second", now=FIXED_NOW)
    p3, _ = notes_store.create_entry("third", now=FIXED_NOW)
    assert p1.name == "14-30-52.md"
    assert p2.name == "14-30-52-2.md"
    assert p3.name == "14-30-52-3.md"
    assert p1.read_text() != p2.read_text()


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


def test_note_date_new_style_and_legacy(notes_folder):
    new, _ = notes_store.create_entry("x", now=FIXED_NOW)
    assert notes_store.note_date(new) == FIXED_NOW
    legacy = _legacy_note(notes_folder, "2026-05-14-205701-my-first-note.md")
    assert notes_store.note_date(legacy) == datetime(2026, 5, 14, 20, 57, 1)


def test_note_date_unparseable_falls_back_to_mtime(notes_folder):
    weird = _legacy_note(notes_folder, "20260513_225818_my_first_note.md")
    got = notes_store.note_date(weird)
    assert got == datetime.fromtimestamp(weird.stat().st_mtime)


def test_list_recent_filters_by_days_and_category(notes_folder, monkeypatch):
    old_now = datetime(2026, 6, 1, 10, 0, 0)
    notes_store.create_entry("old note", now=old_now)
    notes_store.create_entry("fresh plain", now=FIXED_NOW)
    notes_store.create_entry("fresh feeling", category="feelings",
                             now=datetime(2026, 7, 4, 15, 0, 0))
    monkeypatch.setattr(notes_store, "_now", lambda: datetime(2026, 7, 5, 9, 0, 0))

    recent = notes_store.list_recent(days=7)
    texts = [r["text"].strip() for r in recent]
    assert texts == ["fresh feeling", "fresh plain"]  # newest first, no old note

    only_feelings = notes_store.list_recent(days=7, category="feelings")
    assert len(only_feelings) == 1
    assert only_feelings[0]["category"] == "feelings"


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


def test_read_note_refuses_symlink_escape(notes_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    link = notes_folder / "sneaky.md"
    link.symlink_to(secret)
    with pytest.raises(ValueError):
        notes_store.read_note(str(link))
