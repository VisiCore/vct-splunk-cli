# splunk-cli

A small, scriptable command-line tool to read, search, health-check, and safely
administer **Splunk Enterprise** over its documented REST API — built for AI CLI
agents and humans alike.

[![CI][ci-badge]][ci]
[![OpenSSF Scorecard][scorecard-badge]][scorecard]
[![ACS contract][acs-badge]][acs]
[![License: MIT][license-badge]](./LICENSE)
[![Python][python-badge]](https://www.python.org/)
[![Ruff][ruff-badge]](https://github.com/astral-sh/ruff)
[![Checked with pyright][pyright-badge]](https://microsoft.github.io/pyright/)
[![pre-commit][precommit-badge]](https://github.com/pre-commit/pre-commit)
[![Conventional Commits][commits-badge]](https://www.conventionalcommits.org)

[ci]: https://github.com/VisiCore/vct-splunk-cli/actions/workflows/ci.yml
[ci-badge]: https://github.com/VisiCore/vct-splunk-cli/actions/workflows/ci.yml/badge.svg
[scorecard]: https://scorecard.dev/viewer/?uri=github.com/VisiCore/vct-splunk-cli
[scorecard-badge]: https://api.scorecard.dev/projects/github.com/VisiCore/vct-splunk-cli/badge
[acs]: https://github.com/VisiCore/vct-splunk-cli/actions/workflows/acs-contract.yml
[acs-badge]: https://github.com/VisiCore/vct-splunk-cli/actions/workflows/acs-contract.yml/badge.svg
[license-badge]: https://img.shields.io/badge/License-MIT-yellow.svg
[python-badge]: https://img.shields.io/badge/python-3.10%E2%80%933.14-blue.svg
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[pyright-badge]: https://microsoft.github.io/pyright/img/pyright_badge.svg
[precommit-badge]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white
[commits-badge]: https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196?logo=conventionalcommits&logoColor=white

## What this is

Splunk collects and searches machine data such as logs, metrics, and events.
Administering it normally means clicking through a web page or calling a REST
API by hand.

This tool turns that API into one predictable command: `splunk`. A person or an
AI agent can inspect a Splunk server, run searches, and make carefully guarded
changes from a terminal or a script.

Reading is always safe. Anything that changes the server shows you the request
first, asks before acting, and records what it did.

## Before you start

You need two things.

1. **Python 3.10 or newer.** Check with `python3 --version`. If that fails or
   shows an older version, install Python from [python.org](https://www.python.org/downloads/).
   Nothing else is required — the `venv` and `pip` tools used below come with
   Python.
2. **A Splunk server you can reach**, plus a token or a username and password
   for it.

> **Which address?** Use the **management port**, usually `8089`, not the web
> page on `8000`. A correct address looks like `https://your-server:8089`.

## Installation

Run these three commands in the folder where you cloned this repository.

```bash
python3 -m venv .venv                          # create a private Python folder
.venv/bin/python -m pip install -e ".[dev]"    # install the tool and its test tools
.venv/bin/splunk --help                        # check that it works
```

If the last command prints a list of commands, you are done.

Every later command in this file starts with `.venv/bin/`. That prefix runs the
copy of the tool you just installed, so you never have to change anything on the
rest of your computer.

### If you are on Windows

Everything works the same. Three things are spelled differently, in PowerShell:

| macOS and Linux | Windows |
| --- | --- |
| `python3 -m venv .venv` | `py -m venv .venv` |
| `.venv/bin/splunk` | `.venv\Scripts\splunk` |
| `export NAME=value` | `$env:NAME = "value"` |

### If you use Nix

`nix develop` (or `direnv allow`) gives you a shell with Python and `ruff`. Then
run the same three install commands above.

## Connect to Splunk

The tool reads your credentials from environment variables. A secret is never
accepted as a command-line flag, because flags show up in your shell history and
in the process list.

```bash
export SPLUNK_URL="https://your-server:8089"
export SPLUNK_TOKEN="<your Splunk authentication token>"
```

Check the connection:

```bash
.venv/bin/splunk server info
```

### Other ways to sign in

| Variable | When to use it |
| --- | --- |
| `SPLUNK_TOKEN` | Preferred. A Splunk authentication token (a JWT). |
| `SPLUNK_SESSION_KEY` | A session key. `.venv/bin/splunk auth login` creates one. |
| `SPLUNK_USERNAME` + `SPLUNK_PASSWORD` | Last resort. The tool trades them for a session key. |

### If the certificate is not trusted

Lab servers often use a self-signed certificate, which makes the connection fail.

```bash
export SPLUNK_CA_BUNDLE="/path/to/ca.pem"   # best: trust your own certificate
export SPLUNK_VERIFY="false"                 # last resort: skip the check entirely
```

Setting `SPLUNK_CA_BUNDLE` always turns verification **on** against that
certificate, and it overrides `SPLUNK_VERIFY`. To turn checking off completely,
leave `SPLUNK_CA_BUNDLE` unset and set `SPLUNK_VERIFY=false`.

You can also keep settings per server in a configuration **profile** and pick one
with `--profile` or `SPLUNK_PROFILE`. A flag beats an environment variable, which
beats a profile.

## Usage

Commands read as a noun followed by a verb.

```bash
.venv/bin/splunk server info                       # who am I connected to, and what version
.venv/bin/splunk index list                        # list indexes
.venv/bin/splunk index get main                    # details for one index
.venv/bin/splunk search run --query 'index=_internal | stats count by sourcetype' --earliest -1h
.venv/bin/splunk search list                       # search jobs, running and finished
.venv/bin/splunk health check                      # server health; exit code 5 if anything is warn or fail
.venv/bin/splunk saved-search list --app my_app    # saved searches in an app
.venv/bin/splunk api get /services/data/indexes    # raw read-only escape hatch for any endpoint
```

Many objects — `user`, `role`, `monitor-input`, `hec-token`, `macro`,
`eventtype`, `kvstore-collection`, `app`, and more — follow the same pattern.
Run `.venv/bin/splunk --help` to see them all, and `.venv/bin/splunk <name> --help` for one.

### Owners and apps

Most saved searches and knowledge objects live inside an **app**, owned by a
**user**. Two options set that:

```bash
.venv/bin/splunk saved-search list --app my_app --owner nobody          # narrow a read
.venv/bin/splunk saved-search create nightly --search '...' --app my_app # writes need an app
export SPLUNK_APP=my_app SPLUNK_OWNER=nobody                            # or set defaults once
```

Reads search every app by default. **Writes always require you to name an app**,
so an object is never created somewhere you did not intend.

### Changes are guarded

Every command that changes the server behaves the same way:

```bash
.venv/bin/splunk index create payments --dry-run   # show the exact request, send nothing
.venv/bin/splunk index create payments             # ask for confirmation, then do it
.venv/bin/splunk index create payments --yes       # skip the question (required in scripts)
```

In a script with no person watching, a change without `--yes` stops immediately
rather than waiting forever for an answer.

Every applied change is appended to a log file, so you can see what happened.
The tool uses the first of these it finds: `$VCT_SPLUNK_AUDIT`, then
`$XDG_STATE_HOME/vct-splunk/audit.log`, then
`~/.local/state/vct-splunk/audit.log`.

## Output and exit codes

On a terminal you get a readable table. When you pipe the output somewhere, or
pass `--output json`, you get JSON. Data goes to standard output; messages,
questions, and errors go to standard error. That makes this safe:

```bash
.venv/bin/splunk index list --output json | jq '.data[] | select(.disabled) | .name'
```

| Exit code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | API, network, or operation error |
| 2 | You asked for something impossible (for example, a change without `--yes`) |
| 3 | Sign-in failed (401 or 403) |
| 4 | Not found (404) |
| 5 | `health check` ran, but something is warn or fail |

Success prints `{"data": ..., "meta": ...}` and failure prints
`{"error": {"code": ..., "message": ...}}`. Those shapes and the exit codes are a
**stable contract**: new fields and codes may be added, but existing ones are
never renamed or removed, so scripts and agents can depend on them.

## Splunk Cloud

If `SPLUNK_URL` points at a `*.splunkcloud.com` address, the tool notices and
reads through the Cloud ACS API instead. You do not choose a mode, and the
commands are the same.

```bash
export SPLUNK_URL="https://your-stack.splunkcloud.com"
export SPLUNK_ACS_TOKEN="<your ACS token>"
export SPLUNK_ACS_BASE_URL="https://admin.splunkcloudgc.com"   # only for FedRAMP
```

Cloud support is **read-only** today, and covers `index list`, `role list`, and
`hec-token list`. Anything else stops with a clear "not supported here" error
instead of guessing. Run `.venv/bin/splunk inspect` to see which backend your address
resolves to and what it can do. It answers offline, without contacting anything.

## Running the tests

The unit tests need no server, no credentials, and no network:

```bash
.venv/bin/python -m pytest tests/unit
```

Four more groups run against a real server, a real Splunk Cloud stack, or
Splunk's published API description. Each is off until you switch it on.
[tests/TESTING.md](./tests/TESTING.md) gives every group its exact variables
and its exact command.

## Security

Reading can never change your server. Everything that can is gated: `--dry-run`
shows the request, a terminal asks first, a script must pass `--yes`, and every
applied change is recorded in the audit log.

Your secrets — passwords, tokens, and session keys — are read from the
environment or a profile. None of them can be passed as a command-line option,
because options are saved in shell history and are visible to anyone who can
list processes. (`auth login` takes `--username`, which is not a secret; it
reads the password from the environment or a no-echo prompt.) The tool writes
no credential to disk.

Secret values in a server's reply are replaced with `<redacted>` before you see
them, so listing Event Collector tokens shows you which ones exist without
printing any of them. Three commands are deliberate exceptions, because handing
you a new secret is the whole point of running them: `auth login` prints the
session key it just created, `hec rotate` prints the token it regenerated, and
`hec-token create` prints the token it just created. None of those values is
written to the audit log.

To report a vulnerability, see [SECURITY.md](./SECURITY.md). Please do not open
a public issue for one.

## Scope

The certified target is **Splunk Enterprise on premises**, reached with your own
credentials over the documented REST API. This project does not use, bundle, or
proxy any app distributed by Splunk. Splunk Cloud is supported for reading, as
described above.

## Contributing

The code separates a plain Python core from a thin command-line shell:

- `src/vct_splunk/core/` — plain functions and typed errors. Never imports Click.
- `src/vct_splunk/commands/` — the command-line layer, one file per group.

Tests mirror that layout under `tests/unit/` and `tests/integration/`. See
[CONTRIBUTING.md](./CONTRIBUTING.md) for setup and review, and
[AGENTS.md](./AGENTS.md) for architecture and conventions.

## License

[MIT](./LICENSE)

---

More at [docs.jacobpevans.com](https://docs.jacobpevans.com).
