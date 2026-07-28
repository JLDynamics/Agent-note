import io
import json
import sys
import tomllib
from pathlib import Path

import pytest

from agent_note import cli, embeddings, notes_store, service


class BinaryStdin:
    def __init__(self, content):
        self.buffer = io.BytesIO(content)


@pytest.fixture
def notes_folder(tmp_path, monkeypatch):
    folder = tmp_path / "notes"
    folder.mkdir()
    monkeypatch.setattr(notes_store, "get_notes_folder", lambda: folder)
    monkeypatch.setattr(embeddings, "embed_text", lambda text: [1.0, 2.0, 3.0])
    return folder


def run_cli(capsys, argv):
    exit_code = cli.main(argv)
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out)


def test_create_accepts_stdin_and_returns_public_result_shape(
    notes_folder, monkeypatch, capsys
):
    monkeypatch.setattr(
        sys,
        "stdin",
        BinaryStdin("Complete note body ☕\n".encode()),
    )
    exit_code, result = run_cli(
        capsys,
        [
            "create",
            "--input",
            "-",
            "--title",
            "CLI note",
            "--tag",
            "Memory System",
        ],
    )

    assert exit_code == cli.EXIT_OK
    assert set(result) == {
        "path",
        "title",
        "tags",
        "embedded",
        "warning",
    }
    assert result["title"] == "CLI note"
    assert result["tags"] == ["memory-system"]
    assert "Complete note body ☕" in notes_store.read_note(result["path"])


def test_import_file_preserves_utf8_bytes_and_reports_broad_first(
    notes_folder, tmp_path, capsys
):
    source = tmp_path / "conversation.txt"
    raw_bytes = "User: Café ☕\r\nAssistant: Preserved.\r\n".encode()
    source.write_bytes(raw_bytes)

    exit_code, result = run_cli(
        capsys,
        [
            "import",
            "--input",
            str(source),
            "--original-date",
            "2026-07-24",
            "--title",
            "Conversation",
        ],
    )

    assert exit_code == cli.EXIT_OK
    assert result["status"] == "raw_saved"
    assert "broad session handoff" in result["next_action"]
    transcript = Path(result["transcript_path"])
    assert transcript.read_bytes() == raw_bytes


def test_search_recent_tags_and_read_use_core_results(notes_folder, capsys):
    created = service.create_note(
        "OpenClaw gateway notes",
        title="Gateway",
        tags=["OpenClaw", "operations"],
    )

    expected_search = embeddings.search("OpenClaw", limit=5)
    exit_code, search_result = run_cli(
        capsys, ["search", "--query", "OpenClaw", "--limit", "5"]
    )
    assert exit_code == cli.EXIT_OK
    assert search_result == expected_search

    expected_recent = notes_store.list_recent(days=1, tags=["operations"])
    exit_code, recent_result = run_cli(
        capsys, ["recent", "--days", "1", "--tag", "operations"]
    )
    assert exit_code == cli.EXIT_OK
    assert recent_result == expected_recent

    expected_tags = notes_store.list_tags()
    exit_code, tag_result = run_cli(capsys, ["tags"])
    assert exit_code == cli.EXIT_OK
    assert tag_result == expected_tags

    exit_code, read_result = run_cli(
        capsys, ["read", "--path", created["path"]]
    )
    assert exit_code == cli.EXIT_OK
    assert read_result == {
        "path": created["path"],
        "content": notes_store.read_note(created["path"]),
    }


def test_cli_returns_json_and_stable_exit_codes_for_errors(
    notes_folder, tmp_path, capsys
):
    exit_code, result = run_cli(capsys, [])
    assert exit_code == cli.EXIT_USAGE_ERROR
    assert "error" in result

    empty = tmp_path / "empty.txt"
    empty.write_text(" \n", encoding="utf-8")
    exit_code, result = run_cli(
        capsys, ["create", "--input", str(empty)]
    )
    assert exit_code == cli.EXIT_USAGE_ERROR
    assert "empty" in result["error"]

    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    exit_code, result = run_cli(
        capsys, ["read", "--path", str(outside)]
    )
    assert exit_code == cli.EXIT_USAGE_ERROR
    assert "Refused" in result["error"]

    exit_code, result = run_cli(
        capsys, ["import", "--input", str(tmp_path / "missing.txt")]
    )
    assert exit_code == cli.EXIT_OPERATION_ERROR
    assert "error" in result


def test_console_entry_point_is_declared():
    project = Path(__file__).parents[1]
    pyproject = tomllib.loads((project / "pyproject.toml").read_text())
    assert pyproject["project"]["scripts"]["agent-note"] == "agent_note.cli:main"
