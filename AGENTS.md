# AGENTS.md

Guidance for AI agents and human contributors working in this repository.

## What this is

`splunk` is a small, scriptable CLI over the **Splunk Enterprise REST API** —
read, search, health-check, and safely administer an on-prem instance with your
own credentials. It does not bundle or proxy any Splunk-distributed app.

## Quick start

```bash
uv venv
uv pip install -e ".[dev]"   # editable install with dev tools
splunk --help                # or: python -m vct_splunk --help
```

Authentication is environment-only (never a CLI flag):

```bash
export SPLUNK_URL="https://your-search-head:8089"   # REST mgmt port, not :8000
export SPLUNK_TOKEN="<a Splunk JWT auth token>"
```

See `.env.example` for every supported variable.

## Architecture

The package separates a Click-free core from a thin CLI shell (the "functional
core, imperative shell" pattern):

- `src/vct_splunk/core/` — plain functions and typed errors. **Never imports
  Click.** This is the reusable, unit-testable library: `client` (transport,
  auth, retries, pagination, dry-run), `errors`, `audit`, `namespace`
  (owner/app resolution), `resource` (the generic CRUD engine: `Spec`/`Field`/
  `CrudResource`), `backends` + `acs/` (Splunk Cloud ACS support), and one
  module per operation (`server`, `api`, `indexes`, `jobs`, `search`,
  `saved_searches`, `health`).
- `src/vct_splunk/commands/` — Click adapters, one module per hand-written
  command group (`server`, `api`, `index`, `search`, `saved_search`, `health`,
  `inspect`), plus shared plumbing: `context` (the `command` decorator and
  `Ctx`), `output` (rendering, error envelope), `write` (the single gated write
  path), `dispatch` (routes a few reads to Cloud ACS), and `registry` +
  `factory` (resource specs declared as data, turned into generated CRUD
  groups — `user`, `role`, `macro`, the data inputs/outputs, and friends).
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
  found. `health check` exits non-zero when any finding is warn or fail.

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

```bash
pytest                                                # unit tests (mocked HTTP)
SPLUNK_INTEGRATION_TEST=true pytest -m integration    # against a live Splunk
```

Unit tests live in `tests/unit/` and mock the transport; the gated end-to-end
tests in `tests/integration/` need `SPLUNK_URL`, credentials (`SPLUNK_TOKEN`,
or the `SPLUNK_USERNAME` / `SPLUNK_PASSWORD` fallback CI uses), and a reachable
instance.

## Checks before a PR

Run the gate through the project venv (`.venv/bin/...`) — the same binaries CI
calls — or via pre-commit. Do **not** route these through `uv run`: it executes
arbitrary code and is deliberately permission-gated, so it prompts on every call.

```bash
.venv/bin/ruff check .      # lint (never silence a rule — fix it)
.venv/bin/ruff format .     # format
.venv/bin/pyright           # types
.venv/bin/pytest            # tests
```

Or let pre-commit run the whole hook set (installed via `pre-commit install
--install-hooks` after `uv pip install -e ".[dev]"`):

```bash
.venv/bin/pre-commit run --all-files                      # commit-stage gate
.venv/bin/pre-commit run --all-files --hook-stage pre-push # adds pytest
```

The hook set (`.pre-commit-config.yaml`) is the dryvist org-wide Python standard
— ruff + ruff-format + pyright at commit, pytest at pre-push. It is kept in sync
with the Nix definition in `nix-devenv`; see the KEEP IN SYNC banner in that file.
