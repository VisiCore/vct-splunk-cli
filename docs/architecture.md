# Architecture

Developer guide to the vct-splunk-cli codebase. The layout mirrors
`vct-cribl-cli` so downstream applications (e.g. the vizzy web interface) can
embed both API layers the same way.

## Project structure

```text
vct_splunk/
  __init__.py              # Package marker + __version__
  __main__.py              # Entry point for `python -m vct_splunk`
  cli.py                   # Click command tree assembly, `splunk` entry point

  api/
    client.py              # httpx transport stack (AuthTransport, RetryTransport),
                           # SplunkClient, create_client, get/set_client singletons
    endpoint_factory.py    # Generic CRUD Endpoints engine, EndpointConfig/Field
    endpoints/             # Hand-written endpoint modules (14 files)
      server.py, search.py, jobs.py, saved_searches.py, kvstore.py,
      hec.py, apps.py, cluster.py, license.py, deploy.py, lookups.py,
      datamodel.py, health.py, raw.py
    acs/                   # Splunk Cloud ACS management-plane client (reads +
                           # gated index/role/hec-token writes)
      client.py, operations.py

  auth/
    session.py             # Credential resolution + session login, cached per process

  commands/
    command_factory.py     # Generates Click CRUD subcommands from the registry
    registry.py            # Declarative list of factory-generated resources
    context.py             # Shared `command` decorator + Ctx (builds clients)
    write.py               # The single gated write path (confirm + audit)
    dispatch.py            # Routes index/role/hec-token reads (and gated
                           # writes) to ACS on Cloud
    server.py, api.py, auth.py, search.py, saved_search.py, health.py,
    kvstore.py, hec.py, apps.py, cluster.py, shcluster.py, license.py,
    deploy.py, lookup.py, datamodel.py, inspect.py

  config/
    loader.py              # INI profiles + env var + CLI flag merging
    types.py               # SplunkConfig, AuthStatus dataclasses

  output/
    formatter.py           # JSON / table formatting, error envelope, prompts

  utils/
    errors.py              # Typed SplunkError hierarchy with exit codes
    redact.py              # Secret redaction by field name; safe_target for URLs;
                           # public_target additionally hides a Cloud stack name
                           # when VCT_SPLUNK_REDACT_TARGET=1
    namespace.py           # /servicesNS/<owner>/<app>/ path building + policy
    path.py                # Path-segment validation/encoding (traversal-safe)
    validation.py          # KEY=VALUE parsing
    audit.py               # Append-only local audit log for writes
    backends.py            # Enterprise-vs-Cloud deduction from SPLUNK_URL

tests/
  cli_catalog.py           # Single catalog of every command leaf
  unit/                    # pytest + httpx.MockTransport (no mock package)
  integration/             # Live suites, gated behind env vars
```

## Key patterns

### HTTP client transport stack

```text
Request
  -> AuthTransport       (injects Authorization header, per request)
    -> RetryTransport    (retries 429/503, honors Retry-After)
      -> httpx.HTTPTransport (sends request; owns TLS verify settings)
```

`AuthTransport` resolves the credential on every request via
`auth.session.get_auth_header()`:

- `SPLUNK_TOKEN` (a JWT) → `Authorization: Bearer <token>`
- `SPLUNK_SESSION_KEY` → `Authorization: Splunk <key>`
- `SPLUNK_USERNAME`/`SPLUNK_PASSWORD` → a session key minted via
  `/services/auth/login`, cached for 55 minutes and re-minted transparently —
  so a long-running embedding process survives session expiry.

`SplunkClient` wraps the stack with Splunk's envelope concerns: the
`output_mode=json` parameter, `entry[].content` handling hand-off, pagination
(`get_collection`), typed error mapping (401/403 → `AuthError`, 404 →
`NotFoundError`, else `APIError`), and the dry-run gate — `write()` /
`write_json()` return a structured preview and send nothing when
`config.dry_run` is set.

### Embedding (vizzy-style)

```python
from vct_splunk.config.loader import load_config
from vct_splunk.api.client import create_client, set_client, get_client
from vct_splunk.api.endpoints import server, search

cfg = load_config()  # env + profile merging, no network I/O
client = create_client(cfg)  # auth resolved lazily, per request
set_client(client)  # optional process-wide hook

info = server.get_server_info(get_client())
hits = search.run_search(get_client(), "index=_internal | head 5")
```

The CLI itself builds a client per command (via `commands/context.py`) instead
of the singleton, so `--help` and config commands never touch the network.

### Two-tier endpoint design

**Factory endpoints** (`api/endpoint_factory.py`) — a generic `Endpoints` class
with `list/get/create/update/delete` (+ `enable`/`disable`) driven by a
declarative `EndpointConfig`. Two URL scopes:

| Scope        | URL pattern                          |
|--------------|--------------------------------------|
| `global`     | `/services/{path}` (path absolute)   |
| `namespaced` | `/servicesNS/{owner}/{app}/{path}`   |

`Field` entries map friendly CLI options to Splunk form keys (with typing,
scaling, and secret handling) and drive the generated Click options.

**Hand-written endpoints** (`api/endpoints/*.py`) — for resources that need
special logic: search (oneshot jobs, NDJSON export parsing), the KV Store
document store (JSON bodies, no envelope), HEC token rotation (mints a secret),
health checks (multi-dimension verdicts), data model acceleration
(read-modify-write of a JSON sub-document), app install, deployment server,
cluster/license reads, and the raw read-only escape hatch (`raw.py`).

### Command registration

`cli.py` adds the hand-written groups, then loops over
`commands/registry.py:REGISTRY` — a flat list of `EndpointConfig` entries —
and generates a Click group per resource via
`commands/command_factory.py:build_group()`.

To add a standard CRUD resource: add one `EndpointConfig` to `registry.py`.
To add a hand-written command: create `api/endpoints/<thing>.py` +
`commands/<thing>.py`, then register the group in `cli.py`.

### Config priority chain

```text
CLI flags (--base-url, --profile, --app, ...)
  > Environment variables (SPLUNK_URL, SPLUNK_TOKEN, ...)
    > Active profile in $XDG_CONFIG_HOME/vct-splunk/config
      > Built-in defaults
```

### Write safety

Every mutation funnels through `commands/write.py:do_write()`. A real write --
`--dry-run` sends nothing and needs neither gate below -- requires
`SPLUNK_ENABLE_WRITES=true` first, on every backend; there is no CLI flag, so a
saved command line cannot enable one. It then confirms on a TTY or requires
`--yes` when non-interactive, and appends a record to the local audit log.
Reads redact secret-named fields by default; only commands whose purpose is to
mint a credential reveal one. Splunk Cloud targets route supported reads
through ACS; writes there need `SPLUNK_CLOUD_WRITE=true` as well (checked even
for a `--dry-run` preview, since it also proves the object is one of the three
ACS-writable resources -- index, role, hec-token create/update/delete only).

### Error handling

The library raises typed errors (`utils/errors.py`); the `command` decorator in
`commands/context.py` renders them once as a JSON envelope on stderr with the
documented exit codes: 0 ok, 1 API/transport, 2 usage/config, 3 auth,
4 not found, 5 health-check findings.

## Development

```bash
python3 -m venv .venv                       # use a Python linked against OpenSSL
.venv/bin/python -m pip install -e ".[dev]"

.venv/bin/pytest                            # unit tests (httpx.MockTransport)
.venv/bin/ruff check . && .venv/bin/ruff format .
.venv/bin/pyright

.venv/bin/splunk server info                # run the CLI
```

> Note: macOS's system Python 3.9 links LibreSSL 2.8, whose TLS handshake
> stalls against Splunk 10's TLS configuration. Use a Homebrew/python.org
> interpreter (OpenSSL 1.1.1+).

Live suites are documented in [tests/TESTING.md](../tests/TESTING.md).
