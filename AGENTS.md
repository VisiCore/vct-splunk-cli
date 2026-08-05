# AGENTS.md

Guidance for AI agents and human contributors working in this repository.

## What this is

`splunk` is a small, scriptable CLI over the **Splunk Enterprise REST API** —
read, search, health-check, and safely administer an on-prem instance with your
own credentials. It does not bundle or proxy any Splunk-distributed app.

## Quick start

```bash
python3 -m venv .venv                            # `venv` is in the standard library
.venv/bin/python -m pip install -e ".[dev]"      # editable install with dev tools
.venv/bin/splunk --help                          # or: .venv/bin/python -m vct_splunk --help
```

Credentials come from the environment or a selected config profile; secret
credentials are never accepted as CLI flags. See `.env.example` for every
supported variable, and [README.md](./README.md) for connecting to a server.

## Architecture

The package separates a Click-free core from a thin CLI shell (the "functional
core, imperative shell" pattern):

- `src/vct_splunk/core/` — plain functions and typed errors. **Never imports
  Click.** This is the reusable, unit-testable library: `client` (transport,
  auth, retries, pagination, dry-run), `auth` (session login), `profiles`
  (INI profile loading), `errors`, `audit`, `namespace`
  (owner/app resolution), `resource` (the generic CRUD engine: `Spec`/`Field`/
  `CrudResource`), `backends` + `acs/` (Splunk Cloud ACS support), and one
  module per hand-written operation (`server`, `api`, `jobs`, `search`,
  `saved_searches` for dispatch, `health`).
- `src/vct_splunk/commands/` — Click adapters, one module per hand-written
  command group (`server`, `api`, `auth`, `search`, `health`, `inspect`, plus
  `saved_search`'s `run`), plus shared plumbing: `context` (the `command`
  decorator and `Ctx`), `output` (rendering, error envelope), `write` (the
  single gated write path), `dispatch` (routes a few reads to Cloud ACS), and
  `registry` + `factory` (resource specs declared as data, turned into
  generated CRUD groups — `index`, `saved-search`, `user`, `role`, `macro`,
  the data inputs/outputs, and friends).
- `src/vct_splunk/cli.py` assembles the root group and the `splunk` entry point;
  `__main__.py` enables `python -m vct_splunk`.

Dependencies flow one way: `commands` import `core`, never the reverse.

Two cross-cutting ideas to know about:

- **Namespaces.** Namespaced resources take `--app` / `--owner` (or
  `SPLUNK_APP` / `SPLUNK_OWNER`). Reads default to the `-` wildcard; writes
  require an explicit app and never silently default to `search`.
- **Transparent backend.** When `SPLUNK_URL` points at `*.splunkcloud.com`, a
  few reads (`index list`, `role list`, `hec-token list`) route through the
  Cloud ACS API and writes are refused; everything else talks to splunkd REST.
  The backend is deduced from the URL — there is no flag to pick it. `splunk
  inspect` reports what the deduced backend supports, offline.

## Conventions

- Keep modules small and single-purpose. Core functions take an explicit
  `SplunkClient` and return plain data.
- Every public function has a docstring; comment intent, not syntax.
- Output contract: stdout is pure data (table on a TTY, JSON when piped or with
  `--output json`); diagnostics, prompts, and errors go to stderr.
- Exit codes: 0 ok, 1 API/transport, 2 usage/config, 3 auth (401/403), 4 not
  found, 5 `health check` succeeded but some finding is warn or fail.

## Safety

- Writes are gated. Every mutation — index lifecycle, saved-search CRUD and
  `search cancel`, and all factory-generated create/update/delete/enable/
  disable — funnels through one shared path (`commands/write.py`): `--dry-run`
  previews the exact request and sends nothing; otherwise it confirms on a TTY
  or requires `--yes` when non-interactive (it never hangs on a hidden prompt).
- Each applied write is appended to a local audit log: `$VCT_SPLUNK_AUDIT` if
  set, else `$XDG_STATE_HOME/vct-splunk/audit.log`, else
  `~/.local/state/vct-splunk/audit.log`.
- `search run` is bounded by default (time window, row cap, timeout) so an agent
  cannot trigger an unbounded export by accident.

## Testing

`tests/cli_catalog.py` is the single catalog of every command leaf. The unit
matrix and all three live suites read from it, so a new command joins every
suite by being registered once. Unit tests mock the transport with
`httpx.MockTransport` — the library's own facility, so no mocking package is
needed.

[tests/TESTING.md](./tests/TESTING.md) is the runbook: every group, its exact
variables, and its exact command.

## Checks before a PR

```bash
.venv/bin/ruff check .      # lint (never silence a rule — fix it)
.venv/bin/ruff format .     # format
.venv/bin/pyright           # types
.venv/bin/pytest            # tests
```

Or run the whole hook set at once, after
`.venv/bin/pre-commit install --install-hooks`:

```bash
.venv/bin/pre-commit run --all-files                       # commit-stage gate
.venv/bin/pre-commit run --all-files --hook-stage pre-push # adds pytest
```

The hook set (`.pre-commit-config.yaml`) is the dryvist org-wide Python standard.
It is kept in sync with the Nix definition in `nix-devenv`; see the KEEP IN SYNC
banner in that file.
