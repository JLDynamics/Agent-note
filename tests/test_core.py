import pytest

from notes_mcp import core


@pytest.fixture
def notes_dir(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(core, "get_notes_folder", lambda: folder)
    return folder


def test_create_note_with_content(notes_dir):
    result = core.create_note("Buy Milk", "2%")

    assert "buy-milk" in result
    files = list(notes_dir.glob("*.md"))
    assert len(files) == 1
    assert files[0].read_text() == "# Buy Milk\n\n2%\n"


def test_create_note_without_content(notes_dir):
    core.create_note("Empty Note")

    files = list(notes_dir.glob("*.md"))
    assert files[0].read_text() == "# Empty Note\n\n"


def test_list_and_count_notes(notes_dir):
    assert core.list_notes() == "No notes yet."
    assert core.count_notes() == "Total notes: 0"

    core.create_note("First")
    core.create_note("Second")

    listed = core.list_notes().splitlines()
    assert len(listed) == 2
    assert core.count_notes() == "Total notes: 2"


def test_show_note(notes_dir):
    core.create_note("Groceries", "eggs")

    assert core.show_note("Groceries") == "# Groceries\n\neggs\n"
    assert core.show_note("missing") == "No note found with title: missing"


def test_search_notes(notes_dir):
    core.create_note("Shopping", "buy milk")
    core.create_note("Work", "finish report")

    assert "shopping" in core.search_notes("milk").lower()
    assert core.search_notes("vacation") == "No notes found containing: vacation"


def test_delete_note(notes_dir):
    core.create_note("Temp")

    result = core.delete_note("Temp")
    assert "Deleted:" in result
    assert list(notes_dir.glob("*.md")) == []
    assert core.delete_note("Temp") == "No note found with title: Temp"


def test_tag_note(notes_dir):
    core.create_note("Ideas", "brainstorm")

    core.tag_note("Ideas", "work")
    content = core.show_note("Ideas")

    assert "tags: [work]" in content
    assert "# Ideas" in content

    core.tag_note("Ideas", "urgent")
    content = core.show_note("Ideas")
    assert "tags: [work, urgent]" in content


def test_append_note(notes_dir):
    core.create_note("Log", "line one")

    core.append_note("Log", "line two")
    assert core.show_note("Log") == "# Log\n\nline one\nline two\n"


def test_replace_section(notes_dir):
    core.create_note("Draft", "old text here")

    core.replace_section("Draft", "old text", "new text")
    assert "new text here" in core.show_note("Draft")
    assert core.replace_section("Draft", "missing", "x") == "Text not found in note: Draft"


def test_insert_after_heading(notes_dir):
    core.create_note("Doc", "# Title\n\n## Ideas\n\nexisting")

    core.insert_after_heading("Doc", "Ideas", "- new item")
    content = core.show_note("Doc")
    lines = content.splitlines()
    ideas_index = next(i for i, line in enumerate(lines) if line.strip() == "## Ideas")
    assert lines[ideas_index + 1] == "- new item"
    assert core.insert_after_heading("Doc", "Missing", "x").startswith("Heading 'Missing' not found")