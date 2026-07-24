# Contributing

Thanks for helping improve Agent-note.

## Development setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Clone the repository and enter its directory.
3. Run `uv sync`.
4. Run the fast test suite with `uv run pytest`.

The optional real-model test downloads the embedding model and can be run with
`uv run pytest -m slow`.

## Making changes

- Keep notes append-only through the MCP tool surface. Updates should create a
  new complete note rather than editing an existing note.
- Preserve raw imported conversations exactly as supplied. Metadata belongs in
  the separate sidecar file.
- Add or update tests for behavior changes.
- Do not add real notes, transcripts, credentials, machine-specific paths, or
  generated embedding files to the repository.
- Keep pull requests focused and explain any user-visible behavior change.

Before opening a pull request, run:

```bash
uv run pytest
```

For security issues, follow [SECURITY.md](SECURITY.md) instead of posting
sensitive details in a public issue.
