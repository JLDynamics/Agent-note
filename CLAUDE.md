# Agent-note — skill-first local notes

Agent-note uses a repository-owned skill for model judgment and an on-demand
JSON CLI for deterministic operations. Notes are plain Markdown in dated
folders under `~/.notes/` (configurable through `~/.notesrc`) and are searchable
through local FastEmbed embeddings.

Conversation imports preserve an exact raw transcript, then the agent creates
one broad session handoff followed by useful non-duplicate focused notes.

## Operation surface

The CLI provides six commands: `create`, `import`, `search`, `recent`, `tags`,
and `read`. Create/import orchestration lives in `service.py`; storage, search,
and guarded reads remain in their focused modules. No command edits or deletes
an existing note. Updates are new notes containing the complete current
context.

The skill chooses a subject-specific title and a few retrieval-focused tags,
reusing established tags when they fit. One kind tag can be useful, but project
tags, kind tags, and taxonomies are never required. Storage keeps the existing
`title`, `date`, and `tags` frontmatter, accepts zero to eight tags, and
normalizes them. Old category fields remain legacy tags without rewriting
existing files.

## Layout

```text
src/agent_note/
  service.py              deterministic create/import result contracts
  cli.py                  noninteractive JSON command boundary
  conversation_import.py  exact raw conversation storage
  notes_store.py          append-only storage, frontmatter, path guards
  embeddings.py           hybrid search and self-healing local vectors
skills/agent-note/        canonical skill and symlink-safe launcher
tests/                    deterministic fast tests plus opt-in real model test
```

Python imports use `agent_note`; the installed distribution and command use
`agent-note`.

## Run

```bash
uv sync
uv run agent-note tags
```

`skills/agent-note/scripts/agent-note` resolves the canonical repository when
the skill is reached through a directory symlink.

## Test

```bash
uv lock --check
uv run --locked pytest -q
uv run pytest -m slow
```

## Conventions

- **Never add edit/delete commands.** Updates are new complete notes; the
  filesystem remains the manual escape hatch.
- **Never lose a saved note.** Embedding failure does not undo storage.
  Embeddings carry content hashes and are replaced atomically; stale, corrupt,
  or absent vectors rebuild during search. Filenames are claimed with exclusive
  creation so concurrent writers cannot overwrite each other.
- **Never rewrite raw conversations.** Store exact transcript bytes under
  `.raw/conversations/<conversation-id>/conversation.txt`, keep metadata in a
  separate JSON file, and exclude everything under `.raw/` from indexing and
  guarded reads.
- **Complete imports semantically.** Import preserves the raw source. The agent
  identifies the durable items that actually exist, creates one broad handoff
  first, searches related notes, and creates only useful non-duplicate focused
  notes with the exact returned source block. Before completion, check that
  each identified important item is covered without forcing categories or a
  fixed note count.
- **Capture durable meaning, not generic summaries.** Preserve why an idea
  matters and its real constraints, a decision and its reason, or a preference
  and when it applies. Include next steps only when present. Keep facts,
  assumptions, proposals, and unresolved questions distinct.
- **Keep enforcement in code.** Model judgment belongs in the skill, but the
  CLI/service/core must perform validation, safe-path checks, timestamps,
  collision handling, raw preservation, embedding behavior, and structured
  reporting. Do not depend on the model reading source code.
- **Use fake embeddings in unit tests.** The real model belongs only in the
  opt-in slow integration test.
