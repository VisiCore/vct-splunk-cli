# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

This is the 0.2.0 development line (version bumped from 0.0.1).

### Fixed

- `server info` now exits with a clear error (exit 2) when `SPLUNK_URL` points at a
  non-REST endpoint (for example the web UI), instead of returning all-null fields
  with exit 0 (#18).

## [0.0.1] - 2026-06-22

### Added

- Initial `splunk` CLI over the Splunk Enterprise REST API: `server info`,
  `api get`, `index list` / `get` / `create`, `search run`, and `health check`.
- Click-free core (`vct_splunk.core`) with typed errors mapped to exit codes,
  fronted by thin Click adapters (`vct_splunk.commands`).
- Gated writes (`--dry-run`, TTY confirmation, `--yes`) recorded to a local
  audit log.
- TTY-adaptive output: a table on a terminal, JSON when piped or with
  `--output json`.

[Unreleased]: https://github.com/VisiCore/vct-splunk-cli/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/VisiCore/vct-splunk-cli/releases/tag/v0.0.1
