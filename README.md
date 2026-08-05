# splunk-cli

A small, scriptable command-line tool to read, search, health-check, and safely
administer **Splunk** over its documented REST API — built for AI CLI agents and
humans alike.

[![CI][ci-badge]][ci]
[![OpenSSF Scorecard][scorecard-badge]][scorecard]
[![Splunk Cloud API contract][acs-badge]][acs]
[![License: MIT][license-badge]](./LICENSE)
[![Python][python-badge]](https://www.python.org/)

[ci]: https://github.com/VisiCore/vct-splunk-cli/actions/workflows/ci.yml
[ci-badge]: https://github.com/VisiCore/vct-splunk-cli/actions/workflows/ci.yml/badge.svg
[scorecard]: https://scorecard.dev/viewer/?uri=github.com/VisiCore/vct-splunk-cli
[scorecard-badge]: https://api.scorecard.dev/projects/github.com/VisiCore/vct-splunk-cli/badge
[acs]: https://github.com/VisiCore/vct-splunk-cli/actions/workflows/acs-contract.yml
[acs-badge]: https://github.com/VisiCore/vct-splunk-cli/actions/workflows/acs-contract.yml/badge.svg
[license-badge]: https://img.shields.io/badge/License-MIT-yellow.svg
[python-badge]: https://img.shields.io/badge/python-3.9%E2%80%933.14-blue.svg

## What this is

Splunk collects and searches machine data such as logs, metrics, and events.
Administering it normally means clicking through a web page or calling a REST API
by hand. This tool turns that API into one predictable command: `splunk`, so a
person or an AI agent can inspect a server, run searches, and make carefully
guarded changes from a terminal or a script.

Reading is always safe. Anything that changes the server shows you the request
first, asks before acting, and records what it did.

The certified target is **Splunk Enterprise on premises**, reached with your own
credentials; Splunk Cloud is supported for reading. This project does not use,
bundle, or proxy any app distributed by Splunk, and it installs two dependencies:
`click` and `httpx`.

## Installation

You need **Python 3.9 or newer** — check with `python3 --version` — and a Splunk
server you can reach, plus a token or a username and password for it.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
source .venv/bin/activate
splunk --help
```

If that prints a list of commands, you are done. Activating puts `splunk` on your
path, so every example below is just `splunk …`. `venv` and `pip` come with
Python, so nothing else is required. If you use Nix, `nix develop` (or `direnv
allow`) gives you a shell with Python and `ruff`, then the same commands apply.

## Connect to Splunk

Credentials come from the environment. A secret is never accepted as a
command-line flag, because flags are saved in shell history and are visible to
anyone who can list processes.

```bash
export SPLUNK_URL="https://your-server:8089"
export SPLUNK_TOKEN="<your Splunk authentication token>"
splunk server info
```

> **Which address?** Use the **management port**, usually `8089`, not the web
> page on `8000`. A correct address looks like `https://your-server:8089`.

### Other ways to sign in

| Variable | When to use it |
| --- | --- |
| `SPLUNK_TOKEN` | Preferred. A Splunk authentication token (a JWT). |
| `SPLUNK_SESSION_KEY` | A session key. `splunk auth login` creates one. |
| `SPLUNK_USERNAME` + `SPLUNK_PASSWORD` | Last resort. The tool trades them for a session key. |

You can also keep settings per server in a configuration **profile** and pick one
with `--profile` or `SPLUNK_PROFILE`. A flag beats an environment variable, which
beats a profile. See [.env.example](./.env.example) for every supported variable.

### If the certificate is not trusted

Lab servers often use a self-signed certificate, which makes the connection fail.

```bash
export SPLUNK_CA_BUNDLE="/path/to/ca.pem"   # best: trust your own certificate
export SPLUNK_VERIFY="false"                # last resort: skip the check entirely
```

`SPLUNK_CA_BUNDLE` always turns verification **on** against that certificate and
overrides `SPLUNK_VERIFY`. To turn checking off completely, leave
`SPLUNK_CA_BUNDLE` unset and set `SPLUNK_VERIFY=false`.

## Usage

Commands read as a noun followed by a verb.

```bash
splunk server info                       # who am I connected to, and what version
splunk index list                        # list indexes
splunk index get main                    # details for one index
splunk search run --query 'index=_internal | stats count by sourcetype' --earliest -1h
splunk search list                       # search jobs, running and finished
splunk health check                      # server health; exit code 5 if anything is warn or fail
splunk saved-search list --app my_app    # saved searches in an app
splunk api get /services/data/indexes    # raw read-only escape hatch for any endpoint
```

Many objects — `user`, `role`, `monitor-input`, `hec-token`, `macro`,
`eventtype`, `kvstore-collection`, `app`, and more — follow the same pattern. Run
`splunk --help` to see them all, and `splunk <name> --help` for one.

### Owners and apps

Most saved searches and knowledge objects live inside an **app**, owned by a
**user**. Two options set that:

```bash
splunk saved-search list --app my_app --owner nobody           # narrow a read
splunk saved-search create nightly --search '...' --app my_app # writes need an app
export SPLUNK_APP=my_app SPLUNK_OWNER=nobody                   # or set defaults once
```

Reads search every app by default. **Writes always require you to name an app**,
so an object is never created somewhere you did not intend.

### Changes are guarded

Every command that changes the server behaves the same way:

```bash
splunk index create payments --dry-run   # show the exact request, send nothing
splunk index create payments             # ask for confirmation, then do it
splunk index create payments --yes       # skip the question (required in scripts)
```

In a script with no person watching, a change without `--yes` stops immediately
rather than waiting forever for an answer. Every applied change is appended to an
audit log — the first of `$VCT_SPLUNK_AUDIT`,
`$XDG_STATE_HOME/vct-splunk/audit.log`, or `~/.local/state/vct-splunk/audit.log`.

## Output and exit codes

On a terminal you get a readable table. When you pipe the output somewhere, or
pass `--output json`, you get JSON. Data goes to standard output; messages,
questions, and errors go to standard error. That makes this safe:

```bash
splunk index list --output json | jq '.data[] | select(.disabled) | .name'
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
instead of guessing. Run `splunk inspect` to see which backend your address
resolves to and what it can do; it answers offline, without contacting anything.

## Security

Reads cannot change your server, writes are gated and audited, secrets are never
accepted as flags, and secret values in a reply are redacted before you see them.

[SECURITY.md](./SECURITY.md) states each of those precisely, names the deliberate
exceptions, and explains how to report a vulnerability. Please do not open a
public issue for one.

## Testing

The unit tests need no server, no credentials, and no network. Four more groups
run against a real server, a real Splunk Cloud stack, or Splunk's published API
description, and each is off until you switch it on.
[tests/TESTING.md](./tests/TESTING.md) gives every group its exact variables and
its exact command.

## Contributing

[CONTRIBUTING.md](./CONTRIBUTING.md) covers setup, the checks every change must
pass, and how review is assigned. [AGENTS.md](./AGENTS.md) holds the
architecture, conventions, and safety rules.

## License

[MIT](./LICENSE)

---

More at [docs.jacobpevans.com](https://docs.jacobpevans.com).
