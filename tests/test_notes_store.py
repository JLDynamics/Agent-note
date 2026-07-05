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
