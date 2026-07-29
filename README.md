# Agent-note

Agent-note is a skill-first, natural-language memory workflow for coding agents.
You talk to your agent normally:

> “Save this idea as a note.”
>
> “Import this conversation.”
>
> “What did we decide about the deployment plan?”

The agent discovers the shared [`agent-note` skill](skills/agent-note), decides
what should be saved or retrieved, and uses a local command-line tool behind the
scenes for reliable storage, import, and search. You normally do **not** type
Agent-note commands yourself.

Notes remain plain Markdown under `~/.notes/`, and semantic search runs locally
through FastEmbed.

## Everyday use

### Save something

Ask explicitly when information should become durable memory:

The skill turns the information into a complete, useful note with a clear title
and a few retrieval-helpful tags. It preserves the meaning, reasons,
constraints, and uncertainty that will matter when the note is found later
instead of merely shortening the conversation.

Agent-note does not save casual chat without an explicit request.

### Recall something

The agent searches relevant notes, reads complete results when needed, and uses
the newest closely relevant note as current context while retaining older notes
as history.

### Import a conversation

Ask the agent to import the complete conversation or transcript:

The agent preserves the complete source once, creates a broad session handoff,
then creates focused durable notes where useful. See
[Complete conversation import](#complete-conversation-import) for the full
workflow.

## How it works

```text
skills/agent-note/
  SKILL.md                       model reasoning and workflow
  references/durable-capture.md
  references/conversation-import.md
  scripts/agent-note             symlink-safe local launcher
src/agent_note/
  cli.py                         six JSON commands and stable exit codes
  service.py                     deterministic create/import orchestration
  conversation_import.py         exact raw transcript preservation
  notes_store.py                 append-only Markdown storage and path guards
  embeddings.py                  local hybrid search and embedding repair
```

The skill handles judgment: what is durable, how to preserve context and
uncertainty, and which existing notes are relevant. After the agent invokes an
operation, the local CLI and Python modules enforce the deterministic work:
UTF-8 input, validation, configured paths, collision-safe filenames, tag
normalization, raw separation, guarded reads, best-effort embeddings, search
ranking, and structured results.

The default installation runs no background service or transport adapter. Each
operation starts on demand and reads or writes the existing local files
directly.

An optional authenticated remote MCP doorway is also available for clients that
cannot run the local skill, such as Claude on a phone. It is a thin adapter over
the same service functions; it does not replace the skill or duplicate storage.
The doorway is disabled unless every HTTPS and OAuth setting is supplied, and it
binds only to loopback so a separately configured secure tunnel can publish it.
See [Remote MCP doorway](docs/remote-mcp.md) for the security model and setup.

## Install and connect the skill

Requirements:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A shell-capable coding agent that supports repository-owned skills

Clone the repository and install its local environment:

```bash
git clone https://github.com/JLDynamics/Agent-note.git
cd Agent-note
uv sync
```

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
2. Start a fresh agent session so skill discovery refreshes.
3. Try a read-only natural-language request such as “What notes do I have about
   Agent-note?”
4. If troubleshooting, run the linked `scripts/agent-note tags` launcher from
   an unrelated directory and confirm it returns JSON.

Skill discovery and refresh behavior are runtime-specific and should be live
tested. Claude Desktop does not use a watched local skill folder; follow its
supported skill installation flow instead of inventing a filesystem link.

The first embedding operation downloads roughly 90 MB and requires internet
access. Later embedding and search operations use the downloaded model locally.
To initialize it ahead of time:

```bash
uv run python -c "from agent_note.embeddings import embed_text; embed_text('warm up')"
```

## Complete conversation import

Conversation import is a model-plus-command workflow, but the agent performs the
commands behind the scenes:

1. The agent reads the complete source.
2. It invokes `import` once. The command saves the exact supplied UTF-8 bytes
   under `.raw/conversations/<conversation-id>/conversation.txt` and writes
   separate metadata.
3. The agent identifies the genuinely durable ideas, decisions, preferences,
   actions or next steps, corrections, and unresolved questions that actually
   exist.
4. It creates one broad session handoff first, using concise synthesis rather
   than merely shortening the transcript, and ends it with the exact returned
   source block.
5. It searches for the main durable subjects.
6. It creates only useful, non-duplicate focused notes for decisions, projects,
   preferences, actions, next actions, ideas, reviews, and other durable
   context. It preserves why ideas matter, the reasons for decisions, when
   preferences apply, and the uncertainty of assumptions, proposals, and
   unresolved questions. It skips casual chatter, does not label every note a
   summary, and ends every note with the same source block.
7. It briefly checks that each identified important item appears in the broad
   handoff or a focused note, adding or expanding only what is missing. It does
   not copy every turn, force empty categories, or target a fixed note count.
8. It searches for the broad handoff to verify retrieval.

Raw preservation alone is not a completed import. Raw files are not indexed:
they use `.txt`, and everything below `.raw/` is excluded from normal note
indexing and guarded reads.

## Data layout and update model

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

Agent-note never edits or deletes an existing note. An update is a new note
carrying the complete current context; the newest closely relevant note wins
while older versions remain searchable history. “Append-only” describes
Agent-note operations, not operating-system enforcement: files can still be
changed manually.

## Notes, tags, and search

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

Search combines local semantic similarity, keywords, and tag signals. Relevance
stays primary. Results within 0.05 of one another are ordered newest-first, so
a new version of the same idea wins without an unrelated recent note replacing
a clearly relevant older result. Weak pure-semantic matches are omitted, and
unreadable notes are skipped.

Embedding companions include a content hash and are replaced atomically. If a
Markdown note changes manually or an embedding is missing or corrupt, the next
search rebuilds it. A failed embedding never discards a successfully saved
note.

Concurrent saves claim filenames with exclusive creation, so notes created in
the same second receive distinct files rather than overwriting each other.

## Privacy and data handling

Agent-note is local-first, but it is not an encrypted vault:

- Notes, transcripts, metadata, and embedding companions are ordinary
  unencrypted files in the configured notes folder.
- Never commit or publish that folder. It may contain private conversations and
  personal information.
- FastEmbed downloads its model once, then embedding inference stays local.
  Note text and queries are not sent to a hosted embedding API.
- Behind-the-scenes command results can include note text, snippets, metadata,
  and absolute paths.
- Imported transcripts include a checksum for provenance, but Agent-note does
  not currently enforce it.

## Under the hood: CLI and troubleshooting

Most users can skip this section. The agent invokes these commands through the
skill launcher. They remain useful for installation checks, debugging,
automation, and development:

```text
agent-note create --input PATH|- [--title TITLE] [--tag TAG ...]
agent-note import --input PATH|- [--original-date DATE] [--title TITLE]
agent-note search --query QUERY [--limit N] [--tag TAG ...]
agent-note recent [--days N] [--tag TAG ...]
agent-note tags
agent-note read --path NOTE_PATH
```

From the repository root, prefix a command with `uv run`. When using the linked
`skills/agent-note/scripts/agent-note` launcher, use the command arguments
directly.

`create` and `import` read complete UTF-8 bodies from a file or standard input;
they never require a body in a shell argument. Every result, including an
error, is JSON on standard output. Exit status `0` means success, `1` means an
operational failure, and `2` means invalid input or usage. Dependency
diagnostics may still appear on standard error.

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
