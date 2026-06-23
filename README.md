# splunk

A small, scriptable CLI to read, search, health-check, and safely administer
**Splunk Enterprise** over its documented REST API — built for AI CLI agents and humans alike.

[![License](https://img.shields.io/badge/license-see%20LICENSE-blue.svg)](./LICENSE)

## Installation

```bash
uv venv
uv pip install -e ".[dev]"      # editable install with test deps
splunk --help
```

Requires Python 3.10+.

## Usage

Authenticate with environment variables (the token is never passed as a flag):

```bash
export SPLUNK_URL="https://your-search-head:8089"
export SPLUNK_TOKEN="<a Splunk authentication token>"
# optional:
export SPLUNK_CA_BUNDLE="/path/to/ca.pem"   # custom CA for on-prem
export SPLUNK_VERIFY="true"                  # TLS verification (default true)
```

> **TLS precedence:** setting `SPLUNK_CA_BUNDLE` always enables verification
> against that CA and takes precedence over `SPLUNK_VERIFY`. To turn verification
> off entirely (e.g. a self-signed lab cert), leave `SPLUNK_CA_BUNDLE` unset and
> set `SPLUNK_VERIFY=false`.

Commands (singular-noun → verb):

```bash
splunk server info                              # connectivity, identity, version
splunk api get /services/data/indexes           # GET-only raw escape hatch (any read endpoint)
splunk index list                               # list indexes
splunk index get main                           # one index
splunk search run --query 'index=_internal | stats count by sourcetype' --earliest -1h
splunk search run --query 'index=main' --export --max-rows 5000    # bounded stream from the export endpoint
splunk search list                              # running / finished search jobs
splunk search get <sid>                         # one job by SID
splunk search cancel <sid>                      # cancel a job (gated write)
splunk saved-search list --app my_app           # saved searches in an app
splunk saved-search create nightly --search 'index=main | stats count' --app my_app --cron '0 2 * * *'
splunk health check                             # native health; exits non-zero if warn/fail
splunk index create payments --max-gb 50 --frozen-secs 7776000   # gated write
```

Many admin resources — `user`, `role`, `monitor-input`, `hec-token`, `macro`,
`eventtype`, `kvstore-collection`, `app`, and more — are generated CRUD groups. Run
`splunk --help` to list them and `splunk <group> --help` for each.

Output is **TTY-adaptive**: a human-readable table on a terminal, JSON when piped or with
`--output json`. stdout is pure data; diagnostics and prompts go to stderr, so this is safe:

```bash
splunk index list --output json | jq '.data[] | select(.disabled) | .name'
```

### Namespaces (owner + app)

Most search and knowledge objects live in a namespace — an **owner** plus an
**app** (`/servicesNS/<owner>/<app>/...`). Two universal options set it:

```bash
splunk saved-search list --app my_app --owner nobody    # narrow a read
splunk saved-search create nightly --search '...' --app my_app   # writes require an app
export SPLUNK_APP=my_app SPLUNK_OWNER=nobody             # or set defaults once
```

Reads default to the `-` wildcard (every owner and app). **Writes require an
explicit app** and never fall back to the default `search` app, so an object is
never created somewhere you did not intend.

### Writes are gated

Writes (`index create`, `saved-search create`/`update`/`delete`, `search cancel`)
are safe by default:

```bash
splunk index create payments --dry-run         # preview the request; sends nothing
splunk index create payments                    # prompts for confirmation on a TTY
splunk index create payments --yes              # --yes is required when non-interactive
```

A non-interactive write without `--yes` fails fast (exit 2) rather than hanging.
Each applied write is appended to a local audit log (`$VCT_SPLUNK_AUDIT`, else
`~/.local/state/vct-splunk/audit.log`).

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | API / transport / operation error |
| 2 | usage or config error (e.g. write refused without `--yes`) |
| 3 | authentication error (401/403) |
| 4 | not found (404) |
| non-zero | `health check` when any finding is `warn`/`fail` |

### Contract stability

The JSON output — `{"data": ..., "meta": ...}` on success, `{"error": {"code",
"message"}}` on failure — and the exit codes above are a **stable, additive-only
contract**: fields and codes may be added over time, never renamed or removed, so
scripts, AI agents, and a backend service can depend on them. Remote Splunk result
text is treated as data only and never drives a write.

## Scope

The primary, certified target is **Splunk Enterprise on-prem**, using your own credentials
against the documented REST API. It does not use, bundle, or proxy any Splunk-distributed app.

A minimal, **read-only Splunk Cloud (ACS)** slice is included: `splunk cloud indexes` /
`hec-tokens` / `roles` (set `SPLUNK_ACS_STACK` / `SPLUNK_ACS_TOKEN`), and `splunk inspect` reports
which operations each backend supports. Cloud coverage is not yet certified against a live stack,
so confidence there is capped. An MCP wrapper is a planned follow-up.

## Testing

```bash
.venv/bin/python -m pytest                 # unit tests (mocked HTTP)
SPLUNK_INTEGRATION_TEST=true .venv/bin/python -m pytest -m integration   # against a live/Docker Splunk
```

## Contributing

The package separates a Click-free core from a thin CLI shell:

- `src/vct_splunk/core/` — plain functions and typed errors; never imports Click.
- `src/vct_splunk/commands/` — Click adapters (one module per command group) plus
  the shared `context` and `output` helpers.

Keep modules small and single-purpose. Tests mirror this layout under `tests/unit/`
and `tests/integration/`. See [CONTRIBUTING.md](./CONTRIBUTING.md) for setup and the
pre-PR checks, and [AGENTS.md](./AGENTS.md) for the architecture and conventions.

## License

See [LICENSE](./LICENSE).

---

More at [docs.dryvist.com](https://docs.dryvist.com).
