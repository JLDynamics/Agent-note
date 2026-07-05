"""Command-line wrapper for the notes functions."""

import argparse

from notes_mcp import core


def main():
    parser = argparse.ArgumentParser(
        prog="notes",
        description="A simple notes tool. Notes are saved to ~/.notes by default; "
        'set "notes_folder" in ~/.notesrc to change the location.',
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="Create a new note")
    p.add_argument("title")
    p.add_argument("content", nargs="?", default="", help="Optional note body")

    sub.add_parser("list", help="List all notes, newest first")

    p = sub.add_parser("show", help="Show a note's full contents")
    p.add_argument("title")

    p = sub.add_parser("search", help="Search note contents for text")
    p.add_argument("query")

    sub.add_parser("count", help="Count how many notes you have")

    p = sub.add_parser("delete", help="Delete a note")
    p.add_argument("title")

    p = sub.add_parser("tag", help="Add a tag to a note")
    p.add_argument("title")
    p.add_argument("tag")

    p = sub.add_parser("append", help="Append text to the end of a note")
    p.add_argument("title")
    p.add_argument("content")

    p = sub.add_parser("replace", help="Replace a block of text in a note")
    p.add_argument("title")
    p.add_argument("old_text")
    p.add_argument("new_text")

    p = sub.add_parser("insert", help="Insert text right after a heading in a note")
    p.add_argument("title")
    p.add_argument("heading")
    p.add_argument("content")

    args = parser.parse_args()

    if args.command == "create":
        result = core.create_note(args.title, args.content)
    elif args.command == "list":
        result = core.list_notes()
    elif args.command == "show":
        result = core.show_note(args.title)
    elif args.command == "search":
        result = core.search_notes(args.query)
    elif args.command == "count":
        result = core.count_notes()
    elif args.command == "delete":
        result = core.delete_note(args.title)
    elif args.command == "tag":
        result = core.tag_note(args.title, args.tag)
    elif args.command == "append":
        result = core.append_note(args.title, args.content)
    elif args.command == "replace":
        result = core.replace_section(args.title, args.old_text, args.new_text)
    elif args.command == "insert":
        result = core.insert_after_heading(args.title, args.heading, args.content)

    print(result)


if __name__ == "__main__":
    main()