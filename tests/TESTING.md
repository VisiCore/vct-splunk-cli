# Running the tests

Five groups. Only the first needs nothing at all — start there.

| Group | What it checks | What you must provide | Directory |
| --- | --- | --- | --- |
| Unit | Everything, with fake network replies | Nothing | `tests/unit/` |
| Enterprise reads | Every read command against a real server | A reachable Splunk | `tests/integration/enterprise/read/` |
| Enterprise writes | Every change, then undoes it | A **disposable** Splunk | `tests/integration/enterprise/write/` |
| Cloud reads | Every read command against a real Cloud stack | A Cloud stack and an ACS token | `tests/integration/cloud/read/` |
| ACS contract | Whether Splunk changed its public Cloud API | Nothing | `tests/integration/` |

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

Every pull request runs group 1 plus lint and type checks. Pull requests that
touch code also run groups 2 and 3 against a throwaway container. Group 5 runs
weekly. Group 4 runs on a schedule once a Cloud stack is configured. A single
check named **Merge Gate** summarizes all of them.
