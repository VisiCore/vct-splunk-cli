# Contributing

Thanks for contributing to `vct-splunk-cli`. This guide covers local setup, the
checks every change must pass, and how review is assigned.

## Development setup

Setup needs nothing beyond Python 3.10 or newer — `venv` and `pip` are part of
the standard library.

```bash
python3 -m venv .venv                          # Windows: py -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"    # Windows: .venv\Scripts\python -m pip ...
.venv/bin/splunk --help
```

## Before you open a PR

Run the full check suite locally — all four must pass (CI runs the same):

```bash
.venv/bin/ruff check .    # lint — never silence a rule, fix it
.venv/bin/ruff format .   # format
.venv/bin/pyright         # types
.venv/bin/pytest          # unit tests (mocked; no network)
```

Four more test groups run against a live server, a live Splunk Cloud stack, or
Splunk's published API description. Each is off until you switch it on.
[tests/TESTING.md](./tests/TESTING.md) gives every group its exact variables,
its exact command, and the container setup the destructive write lane needs.

## Project layout

The package separates a Click-free core from a thin CLI shell, and the tests
mirror that split. [AGENTS.md](./AGENTS.md) holds the full architecture,
conventions, and safety rules.

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
