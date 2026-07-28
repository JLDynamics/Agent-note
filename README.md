# Agent-note

Agent-note is a skill-first, append-only local note system. The shared
[`agent-note` skill](skills/agent-note) guides model judgment, while one
noninteractive JSON CLI performs storage, raw conversation import, search,
listing, and guarded reads. Notes remain plain Markdown under `~/.notes/` and
semantic search runs locally through FastEmbed.

**Update model:** Agent-note never edits or deletes an existing note. An update
is a new note carrying the complete current context; the newest closely
relevant note wins while older versions remain searchable history. Files are
not protected from normal filesystem access and can still be changed manually.

## Architecture

```text
skills/agent-note/
  SKILL.md                       model reasoning and workflow
  references/conversation-import.md
  scripts/agent-note             symlink-safe CLI launcher
src/agent_note/
  cli.py                         six JSON commands and stable exit codes
  service.py                     deterministic create/import orchestration
  conversation_import.py         exact raw transcript preservation
  notes_store.py                 append-only Markdown storage and path guards
  embeddings.py                  local hybrid search and embedding repair
```

The skill decides what is worth saving, turns it into a durable note that will
remain useful when found later, and selects useful tags. It preserves the
meaning and context instead of merely shortening the source or producing a
generic summary. The CLI and Python modules enforce the deterministic work
after a command is invoked: UTF-8 input, validation, configured paths,
timestamped collision-safe filenames, tag normalization, raw separation,
guarded reads, best-effort embeddings, search ranking, and structured JSON
results.

There is no background service or transport adapter. Each command starts on
demand and reads or writes the existing local files directly.

## Data layout

```text
~/.notes/
  .raw/
    conversations/
      conv-20260720T093000-a1b2c3d4/
        conversation.txt # exact imported transcript
        metadata.json    # ID, dates, title, checksum
  2026-07-04/
    14-30-52.md          # one note
    14-30-52.embedding   # local chunk vectors
```

Configure a different root with:

- `~/.notesrc`: `{"notes_folder": "~/MyNotes"}`
- `~/.notes` when `.notesrc` is absent

Agent-note preserves this existing data format. No data migration is required.

## Privacy and data handling

Agent-note is local-first, but it is not an encrypted vault:

- Notes, transcripts, metadata, and embedding companions are ordinary
  unencrypted files in the configured notes folder.
- Never commit or publish that folder. It may contain private conversations and
  personal information.
- FastEmbed downloads its model once, then embedding inference stays local.
  Note text and queries are not sent to a hosted embedding API.
- CLI results can include note text, snippets, metadata, and absolute paths.
- “Append-only” describes Agent-note operations, not operating-system
  enforcement. Imported transcripts include a checksum for provenance, but
  Agent-note does not currently enforce it.

## CLI

The six commands are:

```text
agent-note create --input PATH|- [--title TITLE] [--tag TAG ...]
agent-note import --input PATH|- [--original-date DATE] [--title TITLE]
agent-note search --query QUERY [--limit N] [--tag TAG ...]
agent-note recent [--days N] [--tag TAG ...]
agent-note tags
agent-note read --path NOTE_PATH
```

`create` and `import` read complete UTF-8 bodies from a file or standard input;
they never require a body in a shell argument. Every result, including an
error, is JSON on standard output. Exit status `0` means success, `1` means an
operational failure, and `2` means invalid input or usage. Dependency
diagnostics may still appear on standard error.

### Notes and tags

Notes accept zero to eight tags. The skill uses only a few tags that materially
help retrieval; eight is a limit, not a target. Storage normalizes them:

- lowercase
- spaces and underscores changed to hyphens
- duplicate and blank tags removed
- maximum 40 characters per tag
- maximum eight unique tags per note

For example, `Memory System` and `conversation_import` become `memory-system`
and `conversation-import`. Favor relevant topic tags and optionally one useful
kind tag such as `idea`, `decision`, `preference`, or `session-handoff`. Reuse
established tags when they fit, but do not force project or kind tags, add tags
for completeness, or build a complex taxonomy. Avoid duplicate, near-synonym,
and noisy tags. Existing category fields remain compatible and are read as
legacy tags without rewriting old notes.

### Search and current information

Search combines local semantic similarity, keywords, and tag signals. Relevance
stays primary. Results within 0.05 of one another are ordered newest-first, so
a new version of the same idea wins without an unrelated recent note replacing
a clearly relevant older result. Weak pure-semantic matches are omitted.
Unreadable notes are skipped.

Embedding companions include a content hash and are replaced atomically. If a
Markdown note changes manually or an embedding is missing or corrupt, the next
search rebuilds it. A failed embedding never discards a successfully saved
note.

Concurrent saves claim filenames with exclusive creation, so notes created in
the same second receive distinct files rather than overwriting each other.

## Complete conversation import

Import is deliberately a model-plus-command workflow:

1. Read the complete source.
2. Run `import` once. The command saves the exact supplied bytes under
   `.raw/conversations/<conversation-id>/conversation.txt` and writes separate
   metadata.
3. Identify the genuinely durable ideas, decisions, preferences, actions or
   next steps, corrections, and unresolved questions that actually exist.
4. Create one broad session handoff first, using concise synthesis rather than
   merely shortening the transcript, and end it with the exact returned source
   block.
5. Search for the main durable subjects.
6. Create only useful, non-duplicate focused notes for decisions, projects,
   preferences, actions, next actions, ideas, reviews, and other durable
   context. Preserve why ideas matter, the reasons for decisions, when
   preferences apply, and the uncertainty of assumptions, proposals, and
   unresolved questions. Skip casual chatter, do not label every note a
   summary, and end every note with the same source block.
7. Briefly check that each identified important item appears in the broad
   handoff or a focused note. Add or expand only what is missing; do not copy
   every turn, force empty categories, or target a fixed note count.
8. Search for the broad handoff to verify retrieval.

Raw preservation alone is not a completed import. Raw files are not indexed:
they use `.txt`, and everything below `.raw/` is excluded from normal note
indexing and guarded reads.

## Install and run

Requirements:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A shell-capable agent that supports repository-owned skills

```bash
git clone https://github.com/JLDynamics/Agent-note.git
cd Agent-note
uv sync

printf 'A complete note body.\n' | \
  uv run agent-note create --input - --title "Example" --tag example
uv run agent-note search --query "example"
```

The first embedding operation downloads roughly 90 MB and requires internet
access. Later embedding and search operations use the downloaded model locally.
To initialize it ahead of time:

```bash
uv run python -c "from agent_note.embeddings import embed_text; embed_text('warm up')"
```

## Install the shared skill

Keep [`skills/agent-note`](skills/agent-note) as the one canonical skill folder.
Its launcher resolves the physical repository path with `pwd -P`, so a
user-level directory symlink works from unrelated projects without copying the
skill or globally installing the Python package.

After confirming the active agent runtime’s user skill directory, create a
directory symlink. Common locally verified paths are:

```bash
AGENT_NOTE_REPO="/absolute/path/to/Agent-note"

# Codex
ln -s "$AGENT_NOTE_REPO/skills/agent-note" \
  "$HOME/.codex/skills/agent-note"

# Claude Code
ln -s "$AGENT_NOTE_REPO/skills/agent-note" \
  "$HOME/.claude/skills/agent-note"
```

Then:

1. Confirm the destination with `readlink`.
2. From an unrelated directory, run the linked
   `scripts/agent-note tags` launcher and confirm JSON output.
3. Start a fresh agent session and invoke `$agent-note`.
4. Test `tags` or `search` before the first write.

Skill discovery and refresh behavior are runtime-specific and should be live
tested. Claude Desktop does not use a watched local skill folder; follow its
supported skill installation flow instead of inventing a filesystem link.

## Development

```bash
uv lock --check
uv run --locked pytest -q
uv run pytest -m slow    # real-model integration test, downloads the model
```

The fast suite uses deterministic fake embeddings. See
[CONTRIBUTING.md](CONTRIBUTING.md) for development guidance and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.

## License

Agent-note is available under the [MIT License](LICENSE).
