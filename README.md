# splunk

A small, scriptable command-line tool to read, search, health-check, and safely
administer **Splunk Enterprise** over its documented REST API — built for AI CLI
agents and humans alike.

[![CI](https://github.com/VisiCore/vct-splunk-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/VisiCore/vct-splunk-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with pyright](https://microsoft.github.io/pyright/img/pyright_badge.svg)](https://microsoft.github.io/pyright/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

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

There are five groups. Only the first needs nothing at all — start there.

| Group | What it checks | What you must provide |
| --- | --- | --- |
| Unit | Everything, with fake network replies | Nothing |
| Enterprise reads | Every read command against a real server | A reachable Splunk |
| Enterprise writes | Every change, then undoes it | A **disposable** Splunk |
| Cloud reads | Every read command against a real Cloud stack | A Cloud stack and ACS token |
| ACS contract | Whether Splunk changed its public Cloud API | Nothing |

Every group is off unless you switch it on — leaving one off is an ordinary,
expected skip, not an error. Once you switch a group on, forgetting one of its
other variables stops the tests and says which one is missing; it never quietly
passes by skipping.

### Group 1: unit tests

No server, no credentials, no network. Run this before anything else.

```bash
.venv/bin/python -m pytest tests/unit
```

### Group 2: Enterprise reads

Read-only, so it is safe against a server you care about.

```bash
export SPLUNK_INTEGRATION_TEST=true
export SPLUNK_URL="https://your-server:8089"
export SPLUNK_TOKEN="<your token>"

.venv/bin/python -m pytest tests/integration/enterprise/read -v
```

### Group 3: Enterprise writes

> **Warning.** This group creates, changes, deletes, and restarts things. Point
> it only at a throwaway server. Never point it at production.

Start a disposable Splunk in Docker and copy in the files the tests need:

```bash
docker run -d --name splunk-test -p 8089:8089 \
  -e SPLUNK_START_ARGS=--accept-license \
  -e SPLUNK_GENERAL_TERMS=--accept-sgt-current-at-splunk-com \
  -e SPLUNK_PASSWORD='Ch4ng3d-CI-Pass!' splunk/splunk:latest

# Splunk takes a few minutes to start. Wait until this prints a result:
until curl -ksf -u "admin:Ch4ng3d-CI-Pass!" \
  https://localhost:8089/services/server/info >/dev/null; do sleep 10; done

FIXTURES=/opt/splunk/var/run/splunk/lookup_tmp
docker exec -u root splunk-test mkdir -p "$FIXTURES"
docker cp tests/data/server/. "splunk-test:$FIXTURES/"
docker exec -u root splunk-test tar -czf "$FIXTURES/vct_ci_app.spl" -C "$FIXTURES" vct_ci_app
docker cp tests/data/server/vct_test_input.sh \
  splunk-test:/opt/splunk/etc/apps/search/bin/vct_test_input.sh
docker exec -u root splunk-test chown -R splunk:splunk \
  "$FIXTURES" /opt/splunk/etc/apps/search/bin/vct_test_input.sh
docker exec -u root splunk-test chmod 755 /opt/splunk/etc/apps/search/bin/vct_test_input.sh
```

Then run the tests:

```bash
export SPLUNK_INTEGRATION_TEST=true
export SPLUNK_WRITE_TEST=true
export SPLUNK_URL="https://localhost:8089"
export SPLUNK_USERNAME=admin
export SPLUNK_PASSWORD='Ch4ng3d-CI-Pass!'
export SPLUNK_VERIFY=false
export SPLUNK_TEST_SERVER_FIXTURE_DIR=/opt/splunk/var/run/splunk/lookup_tmp

.venv/bin/python -m pytest tests/integration/enterprise/write -v
```

Clean up when you are finished: `docker rm -f splunk-test`.

### Group 4: Cloud reads

Read-only. It needs a real Splunk Cloud stack and an ACS token.

```bash
export SPLUNK_ACS_LIVE_TEST=true
export SPLUNK_URL="https://your-stack.splunkcloud.com"
export SPLUNK_ACS_TOKEN="<your ACS token>"
# export SPLUNK_ACS_BASE_URL="https://admin.splunkcloudgc.com"   # only for FedRAMP

.venv/bin/python -m pytest tests/integration/cloud/read -v
```

This runs every read command your Cloud stack could receive. The reads Cloud
serves must succeed. Every other read must fail with a proper error message and
a documented exit code, which is how the tool proves it never guesses at an
endpoint your stack does not offer.

### Group 5: ACS public contract

No credentials. It downloads Splunk's public Cloud API description and reports
whether it changed underneath us.

```bash
export SPLUNK_ACS_SPEC_TEST=true
.venv/bin/python -m pytest tests/integration/test_acs_public_spec.py -v
```

### Checks before you open a pull request

```bash
.venv/bin/ruff check .    # style problems
.venv/bin/ruff format .   # fix formatting
.venv/bin/pyright         # type problems
.venv/bin/pytest          # unit tests
```

Continuous integration runs the same four commands, plus the Enterprise groups
against a throwaway Splunk container. A single check named **Merge Gate**
summarizes every job.

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
