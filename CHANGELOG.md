# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

This is the 0.2.0 development line (version bumped from 0.0.1).

### Added

- Namespace support: universal `--app` / `--owner` options (and `SPLUNK_APP` /
  `SPLUNK_OWNER`) for namespaced resources. Reads default to the `-` wildcard;
  writes require an explicit app and never default to `search`.
- `search list` / `get` / `cancel` for the search-job lifecycle, plus a bounded
  `search run --export` that streams from the export endpoint (#3).
- `saved-search list` / `get` / `create` / `update` / `delete` / `run` (#3).
- `index update` / `delete` / `enable` / `disable` complete the index lifecycle;
  `update` merges server-side, sending only the settings that changed (#2).
- Splunk-CLI verb aliases (`add` / `edit` / `remove`) on the `index` group.
- A single shared write path (`do_write`) behind every mutation, recording each
  applied write to the audit log (first slice of #12).
- A registry/factory engine: CRUD-shaped Splunk resources are described as data
  and become generated command groups. Proven on access — `user`, `role`,
  `capability` (#4).
- Many admin resources as generated CRUD groups: data inputs and outputs, search
  macros, event types, field extractions, lookup definitions, KV Store collection
  schemas, system messages, and app lifecycle (#5, #6, #8, #9, #10).
- An explicit additive-only output-contract statement plus a contract test pinning
  the JSON envelopes, the documented exit codes, and prompt-injection safety (#16).

### Changed

- Factory resource specs are now thin: each one carries just its REST path, so
  you set fields with the generic `--set KEY=VALUE` and Splunk checks them on the
  server. This drops the hand-kept field lists that used to copy Splunk's spec
  and quietly fall out of date.

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
