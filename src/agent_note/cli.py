"""Noninteractive JSON command-line adapter for Agent-note."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_note import embeddings, notes_store, service

EXIT_OK = 0
EXIT_OPERATION_ERROR = 1
EXIT_USAGE_ERROR = 2


class CliUsageError(ValueError):
    """Invalid CLI input that should produce JSON instead of argparse text."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Argument parser whose errors are handled by the JSON output boundary."""

    def error(self, message):
        raise CliUsageError(message)


def _build_parser():
    parser = JsonArgumentParser(
        prog="agent-note",
        description="Create, import, search, list, and read local Agent-note data.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create one append-only note.")
    create.add_argument(
        "--input",
        required=True,
        metavar="PATH|-",
        help="Read the UTF-8 note body from PATH, or from stdin with '-'.",
    )
    create.add_argument("--title")
    create.add_argument("--tag", action="append", dest="tags")
    create.add_argument(
        "--summary",
        help="Store a caller-written factual one- or two-sentence brief summary.",
    )

    import_command = commands.add_parser(
        "import", help="Preserve one complete raw conversation."
    )
    import_command.add_argument(
        "--input",
        required=True,
        metavar="PATH|-",
        help="Read the complete UTF-8 transcript from PATH, or stdin with '-'.",
    )
    import_command.add_argument("--original-date")
    import_command.add_argument("--title")

    search = commands.add_parser("search", help="Search all normal notes.")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--tag", action="append", dest="tags")

    recent = commands.add_parser("recent", help="List recent normal notes.")
    recent.add_argument("--days", type=int, default=7)
    recent.add_argument("--tag", action="append", dest="tags")

    commands.add_parser("tags", help="List normalized tags and usage counts.")

    read = commands.add_parser("read", help="Read one guarded Markdown note path.")
    read.add_argument("--path", required=True)

    return parser


def _read_utf8_input(source):
    if source == "-":
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read()
        if isinstance(data, str):
            return data
    else:
        data = Path(source).expanduser().read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CliUsageError(f"input must be valid UTF-8: {source}") from exc


def _run(args):
    if args.command == "create":
        result = service.create_note(
            _read_utf8_input(args.input),
            tags=args.tags,
            title=args.title,
            summary=args.summary,
        )
        return result, EXIT_USAGE_ERROR if "error" in result else EXIT_OK

    if args.command == "import":
        return (
            service.import_conversation(
                _read_utf8_input(args.input),
                original_date=args.original_date,
                title=args.title,
            ),
            EXIT_OK,
        )

    if args.command == "search":
        return (
            embeddings.search(args.query, limit=args.limit, tags=args.tags),
            EXIT_OK,
        )

    if args.command == "recent":
        return notes_store.list_recent(days=args.days, tags=args.tags), EXIT_OK

    if args.command == "tags":
        return notes_store.list_tags(), EXIT_OK

    if args.command == "read":
        try:
            content = notes_store.read_note(args.path)
        except (ValueError, OSError) as exc:
            return {"error": str(exc)}, EXIT_USAGE_ERROR
        return {
            "path": str(args.path),
            "summary": notes_store.summary_from_note_text(content),
            "content": content,
        }, EXIT_OK

    raise CliUsageError(f"unknown command: {args.command}")


def _emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main(argv=None):
    try:
        args = _build_parser().parse_args(argv)
        payload, exit_code = _run(args)
    except (CliUsageError, ValueError, UnicodeError) as exc:
        payload, exit_code = {"error": str(exc)}, EXIT_USAGE_ERROR
    except OSError as exc:
        payload, exit_code = {"error": str(exc)}, EXIT_OPERATION_ERROR
    except Exception as exc:
        payload, exit_code = {"error": str(exc)}, EXIT_OPERATION_ERROR

    _emit(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
