# Changelog

Notable changes to Agent-note are documented here.

## [0.1.0] - 2026-07-23

Initial public version.

### Added

- Six-tool MCP interface for creating, importing, searching, listing, tagging,
  and reading append-only Markdown notes.
- Local hybrid search with FastEmbed, chunked vectors, keyword and tag signals,
  and automatic repair of stale embedding companions.
- Raw conversation preservation with checksums and derived-note provenance.
- Public installation, privacy, security, and contribution guidance.
- Automated fast-test workflow for pull requests and pushes.

### Safety and portability

- Notes and imported transcripts remain local, unencrypted files under the
  user-configured notes folder.
- Reads exclude raw source material and reject paths outside the notes folder.
- Atomic file creation prevents concurrent writers from overwriting notes.
- Project MCP configuration avoids machine-specific paths.
