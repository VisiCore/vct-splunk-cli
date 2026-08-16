# Running the tests

Six groups. Only the first needs nothing at all — start there.

| Group | What it checks | What you must provide | Directory |
| --- | --- | --- | --- |
| Unit | Everything, with fake network replies | Nothing | `tests/unit/` |
| Enterprise reads | Every read command against a real server | A reachable Splunk | `tests/integration/enterprise/read/` |
| Enterprise writes | Every change, then undoes it | A **disposable** Splunk | `tests/integration/enterprise/write/` |
| Cloud reads | Every read command against a real Cloud stack | A Cloud stack and an ACS token | `tests/integration/cloud/read/` |
| ACS contract | Whether Splunk changed its public Cloud API | Nothing | `tests/integration/` |
| Fuzz | That a credentialed URL never survives redaction | Linux on x86_64 | `tests/fuzz/` |

Every group is off unless you switch it on. Leaving one off is an ordinary,
expected skip, not an error. Once you switch a group on, forgetting one of its
other variables stops the tests and names the missing one; it never quietly
passes by skipping.

All commands below run from the repository root, after the install in
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Group 1: unit tests

No server, no credentials, no network. Run this before anything else.

```bash
.venv/bin/python -m pytest tests/unit
```

### The Splunk Cloud contract, without a Splunk Cloud stack

Two files in this group cover the Cloud path in full, so you can check it
without an account:

```bash
.venv/bin/python -m pytest tests/unit/test_acs_loopback.py       # every Cloud read
.venv/bin/python -m pytest tests/unit/test_cloud_write_refusal.py # every Cloud write
```

`test_acs_loopback.py` starts a small HTTP server on a loopback port, points
the tool's Cloud address at it, and runs each read command the whole way
through. Nothing is stubbed out, so it checks the address the tool builds, the
token it sends, and that a returned secret never reaches your screen.

`test_cloud_write_refusal.py` runs every command that changes something against
a Cloud address, in the form that would really do it, and fails if any of them
so much as opens a connection.

Group 4 below is what these cannot be: proof that a real stack answers the way
Splunk's specification says it does.

## Group 2: Enterprise reads

Read-only, so it is safe against a server you care about.

```bash
export SPLUNK_INTEGRATION_TEST=true
export SPLUNK_URL="https://your-server:8089"
export SPLUNK_TOKEN="<your token>"

.venv/bin/python -m pytest tests/integration/enterprise/read -v
```

## Group 3: Enterprise writes

> **Warning.** This group creates, changes, deletes, and restarts things. Point
> it only at a throwaway server. Never point it at production.

Start a disposable Splunk in Docker and copy in the files the tests need.

<!-- KEEP IN SYNC: .github/workflows/ci.yml "Stage server fixtures" runs the
     same steps against its service container. A workflow cannot source a
     document, so the recipe exists in exactly these two places. -->

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

## Group 4: human-operated Splunk Cloud validation

This is the approval runbook for a real Splunk Cloud stack. It is read-only and
requires no AI or interpretation service: a person runs the commands, checks
the stated results, and completes the sign-off table at the end.

The guaranteed Cloud surface is `inspect`, `index list`, `role list`, and
`hec-token list`. Search-head REST is a separate, optional check because it
needs a second credential and a different network path.

### 1. Prepare a clean local environment

Start at the repository root on the revision you intend to approve. Python 3.9
or newer is the only prerequisite.

```bash
git status --short --branch
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

`git status` must name the expected revision or branch and show no unexpected
changes. The install must finish successfully.

### 2. Prove the Cloud contract without credentials

Run the local end-to-end Cloud routes, every Cloud write refusal, and the
current public ACS OpenAPI contract:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_acs_loopback.py \
  tests/unit/test_cloud_write_refusal.py \
  -q --tb=short

SPLUNK_ACS_SPEC_TEST=true .venv/bin/python -m pytest \
  tests/integration/test_acs_public_spec.py \
  -q --tb=short
```

Both commands must end in `passed`, with no failures or errors. These checks
send no request to your stack; the second command downloads Splunk's public API
description from `admin.splunk.com`.

### 3. Connect to ACS

You need the stack URL and a short-lived ACS JWT whose role can list indexes,
roles, and HEC tokens. If ACS access is restricted by an IP allow list, the
computer running this runbook must already be allowed.

Clear profile and Splunk REST credentials first so they cannot silently affect
the ACS-only result. The Python prompt hides the token and keeps it out of shell
history:

```bash
unset SPLUNK_PROFILE VCT_SPLUNK_CONFIG
unset SPLUNK_TOKEN SPLUNK_SESSION_KEY SPLUNK_USERNAME SPLUNK_PASSWORD
unset SPLUNK_ACS_STACK SPLUNK_ACS_BASE_URL

export SPLUNK_ACS_LIVE_TEST=true
export SPLUNK_URL="https://your-stack.splunkcloud.com"
export SPLUNK_ACS_TOKEN="$(
  .venv/bin/python -c 'import getpass; print(getpass.getpass("ACS token: "))'
)"
```

For FedRAMP IL2, set the alternate ACS origin after the block above:

```bash
export SPLUNK_ACS_BASE_URL="https://admin.splunkcloudgc.com"
```

Do not add `:8089` yet. The ACS checks use the normal Cloud stack URL.

### 4. Exercise every supported ACS command

Run each public command directly so the human approver can see its output:

```bash
.venv/bin/splunk inspect --output json
.venv/bin/splunk index list --output json
.venv/bin/splunk role list --output json
.venv/bin/splunk hec-token list --output json
```

Every command must exit `0` and print a top-level `data` and `meta` object.
`inspect` must report the `cloud` backend and the intended stack. A secret field
in HEC output must contain `<redacted>`; an actual token value must never appear.

Now exercise every catalogued read through the same public CLI:

```bash
.venv/bin/python -m pytest \
  tests/integration/cloud/read/test_catalog.py \
  -q --tb=short
```

The command must end in `passed`, with no failure, error, traceback, or
undocumented exit code. With only the ACS credential configured, non-ACS reads
stop at their documented credential or unsupported-backend boundary.

### 5. Optionally validate search-head REST

Run this section only when the stack exposes its search-head API. It requires:

- port `8089` open for the deployment;
- this computer on the `search-api` IP allow list; and
- a short-lived Splunk authentication token, separate from the ACS token.

Free-trial Cloud stacks do not expose this API. Mark this section `N/A` when a
prerequisite is intentionally unavailable; do not weaken TLS verification.

```bash
export SPLUNK_URL="https://your-stack.splunkcloud.com:8089"
export SPLUNK_TOKEN="$(
  .venv/bin/python -c 'import getpass; print(getpass.getpass("Splunk REST token: "))'
)"

.venv/bin/splunk search run \
  --query '| makeresults | stats count' \
  --earliest -5m \
  --latest now \
  --max-rows 5 \
  --timeout 60 \
  --export \
  --output json

.venv/bin/python -m pytest \
  tests/integration/cloud/read/test_catalog.py \
  -q --tb=short
```

The bounded search must exit `0` and return one result. The catalog must again
end in `passed`; this run carries both credentials and therefore reaches the
full dispatch path available to the stack.

### 6. Clean up credentials and approve the run

```bash
unset SPLUNK_ACS_LIVE_TEST SPLUNK_ACS_TOKEN SPLUNK_ACS_STACK SPLUNK_ACS_BASE_URL
unset SPLUNK_URL SPLUNK_TOKEN SPLUNK_SESSION_KEY SPLUNK_USERNAME SPLUNK_PASSWORD
```

Revoke both short-lived tokens in Splunk Cloud. These read-only commands create
no durable Cloud object and no local write-audit record.

Record `PASS`, `FAIL`, or `N/A` beside each row. Overall approval is `PASS` only
when every required row passes and the cleanup is complete.

| Check | Required result | Result |
| --- | --- | --- |
| Revision and clean checkout | Intended revision; no unexpected changes | |
| Credential-free Cloud routes and write refusals | Pytest passed | |
| Public ACS OpenAPI contract | Pytest passed | |
| Backend inspection | `cloud` and intended stack | |
| Index list | Exit 0; `data` + `meta` | |
| Role list | Exit 0; `data` + `meta` | |
| HEC token list | Exit 0; secrets absent or `<redacted>` | |
| ACS-only CLI catalog | Pytest passed | |
| Search-head REST | Bounded search and full catalog passed, or justified N/A | |
| Cleanup | Variables unset and short-lived tokens revoked | |
| **Overall approval** | **PASS** | |

## Group 5: ACS public contract

No credentials. It downloads Splunk's public Cloud API description and reports
whether it changed underneath us.

```bash
export SPLUNK_ACS_SPEC_TEST=true
.venv/bin/python -m pytest tests/integration/test_acs_public_spec.py -v
```

## Group 6: fuzz

`core.redact.safe_target` is what keeps a password in `SPLUNK_URL` out of
prompts, JSON metadata, and the audit log, and it receives the URL exactly as
typed — before anything validates that it parses. This group generates
malformed targets around a marker password and asserts the marker never comes
back and the call never raises.

It is not part of group 1 and pytest does not collect it: the file is named
`fuzz_redact.py`, and atheris publishes manylinux x86_64 wheels only. On macOS
or arm64 it cannot be installed, which is why it is absent from the `dev`
extra. On Linux:

```bash
.venv/bin/python -m pip install --require-hashes -r requirements-fuzz.txt
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python tests/fuzz/fuzz_redact.py -max_total_time=60
```

## How the suites are organized

`tests/cli_catalog.py` is the single catalog of every command leaf, with the
representative arguments each one needs. The unit matrix and all three live
suites read from it, so a new command joins every suite by being registered
once rather than by being remembered in four places.

Unit tests mock the transport with `httpx.MockTransport` — the library's own
test facility, so no mocking package is needed. The Enterprise read suite
invokes every read leaf; the write suite invokes every mutation, restores
global state, fails on a cleanup leak, and restarts Splunk last.

## What continuous integration runs

Every pull request runs group 1 — including the two Cloud contract files above
— plus lint and type checks. Pull requests that touch code also run groups 2,
3, and 6 against a throwaway container and a Linux runner. Groups 4 and 5 run
weekly; group 4 reports
that there is nothing to certify until a Cloud stack is configured, rather than
passing without checking anything. A single check named **Merge Gate**
summarizes the pull-request jobs.
