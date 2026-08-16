# Contributing

Thanks for contributing to `vct-splunk-cli`. This guide covers local setup, the
checks every change must pass, and how review is assigned.

## Development setup

Setup needs nothing beyond Python 3.9 or newer — `venv` and `pip` are part of
the standard library.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"    # editable install with dev tools
source .venv/bin/activate                      # puts `splunk` and the tools on your path
splunk --help
```

## Before you open a PR

Run the full check suite locally — all four must pass (CI runs the same):

```bash
ruff check .    # lint — never silence a rule, fix it
ruff format .   # format
pyright         # types
pytest          # unit tests (mocked; no network)
```

Continuous integration runs the same hook set in one command, which you can too:

```bash
pre-commit run --all-files
```

Five more test groups run against a live server, a live Splunk Cloud stack,
Splunk's published API description, or a fuzzer. Each is off until you switch it
on. [tests/TESTING.md](./tests/TESTING.md) gives every group its exact
variables, its exact command, and the container setup the destructive write lane
needs.

## If you change a dependency

Install with `pip install -e ".[dev]"` as above — that has not changed. But CI
installs from `requirements-ci.txt`, a hash-pinned lock, so that a replaced
release on PyPI cannot change what CI runs. After editing dependencies in
`pyproject.toml`, regenerate it, or CI keeps resolving the old versions:

```bash
uv pip compile requirements-ci.in --generate-hashes \
  --no-emit-package vct-splunk-cli --python-version 3.14 -o requirements-ci.txt
```

`requirements-fuzz.txt` is the same idea for the fuzz job; its header carries
its own command. Both `.in` files list `.`, so version bounds stay declared once
in `pyproject.toml`.

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
