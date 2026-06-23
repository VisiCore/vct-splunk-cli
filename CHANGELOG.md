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
- `kvstore records` / `get` / `insert` / `update` / `delete` / `purge` manage KV
  Store data records as a namespaced JSON document store; writes require an app (#9).
- `cluster status` and `shcluster status` read indexer-cluster and search-head
  cluster health, and `license list` / `get` / `usage` report licensing (#10).
- `server restart` and `server settings get` / `set` manage the instance.
  `restart` and `settings set` are gated writes, so they preview with `--dry-run`
  and require `--yes` when run non-interactively (#10).
- An explicit additive-only output-contract statement plus a contract test pinning
  the JSON envelopes, the documented exit codes, and prompt-injection safety (#16).
- A minimal, read-only Splunk Cloud (ACS) slice: `cloud indexes` / `hec-tokens` /
  `roles`, plus `inspect` reporting each backend's supported operations. Cloud
  coverage is not yet certified (no live canary); confidence is capped (#27).
- A Dockerized `splunk/splunk` CI integration job (current plus an older release)
  running real create -> verify -> cleanup, with integration coverage for the
  namespaced saved-search and factory user lifecycles (#14).
- A Nix flake dev shell (`nix develop` / direnv) per the workspace convention (#15).
- Deeper health checks (resource usage, disk space, internal-error rate) shipped as
  versioned check data (#11).
- Session-key auth: a credential in `SPLUNK_SESSION_KEY` is sent as
  `Authorization: Splunk <key>` (alongside the existing `SPLUNK_TOKEN` ->
  `Authorization: Bearer <token>`), plus `auth login` (exchange a
  username/password for a session key) and `auth status` (report the resolved
  target and active scheme without revealing the secret) (#13).
- Config-file profiles: a `--profile` option (and `$SPLUNK_PROFILE`) selects a
  named section in an INI file (`$VCT_SPLUNK_CONFIG`, else
  `$XDG_CONFIG_HOME/vct-splunk/config`) supplying `url` / `token` /
  `session_key` / `app` / `owner`. Precedence is flag > env > profile > default,
  so a profile only fills gaps and never overrides an explicit flag or env (#13).

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
