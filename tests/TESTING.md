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

## Group 4: Cloud reads

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

Supplying `SPLUNK_TOKEN` as well exercises the reads Cloud does not serve
through the full dispatch path. Without it they stop earlier, at the
credential check.

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
