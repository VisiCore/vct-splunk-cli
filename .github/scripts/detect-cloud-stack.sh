#!/usr/bin/env bash
# Decide what the Splunk Cloud read canary can certify with the secrets present.
# Writes `ready` and `full` to $GITHUB_OUTPUT.
#
# Two credentials matter, and they certify different things:
#   SPLUNK_URL + SPLUNK_ACS_TOKEN  the reads Cloud serves through ACS
#   SPLUNK_TOKEN                   the reads it does not, which need a splunkd
#                                  credential to reach the dispatch layer at all
#
# Without the second, most of the catalogue stops at the credential check and
# the run looks greener than it is. That case still runs -- the ACS reads are
# worth certifying -- but it says plainly what it did not cover.
#
# Requires: GITHUB_OUTPUT (Actions). Reads SPLUNK_URL, SPLUNK_ACS_TOKEN, SPLUNK_TOKEN.
set -euo pipefail

: "${GITHUB_OUTPUT:?GITHUB_OUTPUT must be set by GitHub Actions}"

note() {
  echo "$1"
  echo "$1" >>"${GITHUB_STEP_SUMMARY:-/dev/null}"
}

if [ -z "${SPLUNK_URL:-}" ] || [ -z "${SPLUNK_ACS_TOKEN:-}" ]; then
  echo "ready=false" >>"$GITHUB_OUTPUT"
  echo "full=false" >>"$GITHUB_OUTPUT"
  note "No Splunk Cloud stack configured, so there is nothing to certify."
  note "The Cloud read and write contracts still run on every pull request, in"
  note "tests/unit/test_acs_loopback.py and tests/unit/test_cloud_write_refusal.py."
  exit 0
fi

echo "ready=true" >>"$GITHUB_OUTPUT"

if [ -n "${SPLUNK_TOKEN:-}" ]; then
  echo "full=true" >>"$GITHUB_OUTPUT"
  note "Certifying every catalogued read against the configured Splunk Cloud stack."
else
  echo "full=false" >>"$GITHUB_OUTPUT"
  note "PARTIAL RUN: no SPLUNK_TOKEN, so only the ACS-served reads are certified."
  note "Every other read stops at the splunkd credential check instead of reaching"
  note "the dispatch layer. Add SPLUNK_TOKEN to certify the full catalogue."
fi
