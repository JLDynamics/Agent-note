# Changelog

Notable changes to Agent-note are documented here.

## [Unreleased]

### Changed

- Replaced the transport-based interface with one repository-owned skill and a
  six-command, noninteractive JSON CLI.
- Moved deterministic create and conversation-import orchestration into a
  reusable service layer while preserving the existing Markdown, raw
  transcript, metadata, embedding, and search formats.

### Removed

- The legacy FastMCP server adapter, project server registrations, and
  transport-only dependency and tests.

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
- The original project server configuration avoided machine-specific paths.
