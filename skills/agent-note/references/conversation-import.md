# Conversation import workflow

Use this workflow only for a complete conversation or source record that the
user explicitly wants saved.

## Prepare the source

1. Read the complete source before importing it. Know whether it is a verbatim
   transcript or a structured, non-verbatim record.
2. Preserve the supplied text exactly. Do not clean, summarize, reformat, or
   add metadata inside the raw transcript.
3. Pass the source through a UTF-8 file or standard input. Never place the
   transcript in a shell argument.

If the source exists only in chat context and the runtime cannot stream standard
input, write the complete text to a private temporary UTF-8 file, import that
file once, and remove the temporary copy after verifying the raw save.

## Preserve once

Run:

```text
<skill-directory>/scripts/agent-note import --input <source-path> \
  [--original-date YYYY-MM-DD] [--title "Conversation title"]
```

Retain these returned values:

- `conversation_id`
- `transcript_path`
- `metadata_path`
- `source_block_for_notes`

Do not import the same source again during one workflow. Agent-note currently
does not deduplicate repeated imports automatically.

## Derive searchable notes

1. Before drafting notes, identify the conversation's genuinely durable items:
   ideas, decisions, preferences, actions or next steps, corrections, and
   unresolved questions—but only when they exist. Use this as a lightweight
   working list, not a form with required categories.
2. Create one broad session handoff as the first derived note. Cover the main
   themes, decisions, projects, preferences, actions and next actions, ideas,
   useful reviews, and unresolved questions. Use concise synthesis rather than
   merely shortening the transcript. Give it a subject-specific title; use
   `session-handoff` only when that kind tag helps retrieval. Skip casual
   chatter.
3. End the broad handoff with the exact `source_block_for_notes`.
4. Search for the main durable subjects before writing focused notes. Use
   results to avoid duplicating focused notes.
5. Create focused standalone notes only for durable subjects that will improve
   future retrieval. Preserve the useful shape of each idea, decision,
   preference, or other subject. Combine closely related facts. Do not create a
   note for every conversational turn or label every note a summary.
6. End every focused note with the same exact source block.
7. Use `create --input PATH|- --title ... --tag ...` for each note. The CLI,
   not prose instructions, must perform validation, timestamping, path
   selection, append-only creation, and best-effort embedding.

Keep established facts distinct from assumptions, proposals, and unresolved
questions in both the broad handoff and focused notes. Do not turn speculation
into fact or invent a next step that was not present.

## Verify and report

1. Confirm every `create` result has a path and no `error`.
2. Do a brief coverage check against the working list. Ensure each identified
   important item appears in the broad handoff or an appropriate focused note;
   add or expand only what is missing.
3. Do not copy every turn, create a note per sentence, use a fixed note count,
   or force empty categories during the coverage check.
4. Search using a broad topic query and confirm the session handoff is returned.
5. Use `read` for any truncated result that needs verification.
6. Report the raw conversation location, broad handoff, focused notes created,
   and anything intentionally omitted.

Do not report the import as complete after only receiving `raw_saved`.
