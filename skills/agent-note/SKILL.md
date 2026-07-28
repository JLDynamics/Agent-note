---
name: agent-note
description: Use Agent-note's local CLI to create, search, list, and read durable notes or import complete conversations. Trigger when the user explicitly asks to remember or save something, asks to recall prior notes or decisions, supplies a conversation for durable import, or needs saved-session continuity. Do not save casual chat without an explicit request.
---

# Agent-note

Use model judgment for meaning and the bundled launcher for every deterministic
storage, import, search, and read operation.

## Command boundary

- Locate this skill's directory from the loaded `SKILL.md`.
- Invoke `scripts/agent-note` relative to that directory. The launcher resolves
  the canonical repository even when this skill directory is reached through a
  symbolic link.
- Send note bodies and transcripts through `--input PATH` or `--input -` with
  standard input. Never place a body or transcript directly in shell arguments.
- Parse JSON from standard output and check the exit status. Do not claim
  success when the command returns a nonzero status or an `error` field.
- If the launcher cannot run, report the error and stop. Do not bypass the CLI
  by writing note-store files directly.

Do not create, edit, delete, or search note-store files directly. The CLI
enforces the configured root, append-only filename claims, raw-source
separation, tag normalization, guarded reads, and embedding behavior.

## Save

1. Save only when the user explicitly requests durable capture.
2. Read [references/durable-capture.md](references/durable-capture.md). Turn
   user-provided information into a durable, useful note that remains valuable
   when found later; do not merely shorten it or produce a generic summary.
3. Choose a clear, subject-specific title. Run `tags` and reuse established
   tags when they fit.
4. Use only a few tags that help retrieval, optionally including one useful
   kind tag. Do not fill the tag allowance or force a taxonomy.
5. Write complete standalone content with `create`. An update is a new complete
   note, never a fragment or an edit to an earlier file.
6. Treat `embedded: false` as a warning, not data loss; the note still saved.

## Recall

1. Run `search` with the user's topic. Use `recent` only for time-based review
   and `tags` for tag discovery.
2. Keep relevance primary. Among closely relevant notes, prefer the newest
   complete note as current and treat older notes as history.
3. Run `read` when a result says `truncated: true` or exact full content matters.
4. Never let a newer unrelated note override an older relevant one.

## Import a complete conversation

Read [references/durable-capture.md](references/durable-capture.md) and
[references/conversation-import.md](references/conversation-import.md) before
importing. Preserve the complete source once, create one broad session handoff
as the first derived note, then create only useful non-duplicate focused notes.
Raw preservation alone is not completion.

## Privacy

Assume note text, transcripts, metadata, embedding companions, and returned
absolute paths are private local data. Do not publish or copy them to a public
repository. Never save credentials, secrets, tokens, or authentication
material.
