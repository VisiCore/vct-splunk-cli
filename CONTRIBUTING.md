# Contributing

Thanks for contributing to `vct-splunk-cli`. This guide covers local setup, the
checks every change must pass, and how review is assigned.

## Development setup

```bash
uv venv
uv pip install -e ".[dev]"
splunk --help        # or: python -m vct_splunk --help
```

## Before you open a PR

Run the full check suite locally — all four must pass (CI runs the same):

```bash
ruff check .       # lint — never silence a rule, fix it
ruff format .      # format
pyright            # types
pytest             # unit tests (mocked; no network)
```

The live suites are independently gated and need a reachable Splunk Enterprise:

```bash
SPLUNK_INTEGRATION_TEST=true pytest -m "integration and enterprise and read"
SPLUNK_INTEGRATION_TEST=true SPLUNK_WRITE_TEST=true \
  pytest -m "integration and enterprise and write"
```

The write lane is destructive and is intended only for the disposable
`splunk/splunk:latest` container. It exercises every mutation through the CLI,
restores global state, fails cleanup leaks, and restarts Splunk last.

The read-only Cloud canary needs `SPLUNK_URL` and `SPLUNK_ACS_TOKEN`:

```bash
SPLUNK_ACS_LIVE_TEST=true pytest -m "integration and cloud and read"
```

## Project layout

The package separates a Click-free core from a thin CLI shell. See
[AGENTS.md](./AGENTS.md) for the full architecture, conventions, and safety
rules. In short:

- `src/vct_splunk/core/` — pure, Click-free library and typed errors.
- `src/vct_splunk/commands/` — Click adapters, one module per command group.
- `tests/unit/` and `tests/integration/` mirror the package.

## Conventions

- Match the surrounding style; keep modules small and single-purpose.
- Every public function has a docstring; comment intent, not syntax.
- Keep stdout pure data and send diagnostics to stderr.
- Writes stay gated (`--dry-run`, confirmation, `--yes`) and audited.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org)
  (`feat:`, `fix:`, `refactor:`, …), imperative mood, no emoji.
- Add a bullet under `## [Unreleased]` in [CHANGELOG.md](./CHANGELOG.md) for any
  user-visible change.

## Review assignment

Reviewers are auto-assigned by path through
[`.github/CODEOWNERS`](./.github/CODEOWNERS):

- Most changes are owned by the default maintainer.
- The CLI surface — commands exposed by the CLI and the REST endpoints they call
  (`src/vct_splunk/cli.py`, `src/vct_splunk/commands/`, `src/vct_splunk/core/`) —
  additionally requires review from the CLI-surface owner. Adding a new object or
  changing a command will request that reviewer automatically.
