#!/usr/bin/env bash
# Decide whether a Splunk Cloud stack is configured for the read canary.
# Writes `ready=true` or `ready=false` to $GITHUB_OUTPUT.
#
# The canary needs real credentials that this project cannot supply for itself.
# Reporting that plainly is better than a green run that checked nothing, so the
# workflow ends as an explicit no-op until the secrets exist.
#
# Requires: GITHUB_OUTPUT (Actions). Reads SPLUNK_URL and SPLUNK_ACS_TOKEN.
set -euo pipefail

: "${GITHUB_OUTPUT:?GITHUB_OUTPUT must be set by GitHub Actions}"

if [ -n "${SPLUNK_URL:-}" ] && [ -n "${SPLUNK_ACS_TOKEN:-}" ]; then
  echo "ready=true" >>"$GITHUB_OUTPUT"
  echo "Splunk Cloud stack configured: certifying the live read path."
else
  echo "ready=false" >>"$GITHUB_OUTPUT"
  echo "No Splunk Cloud stack configured, so there is nothing to certify."
  echo "The Cloud read and write contracts are proved on every pull request by"
  echo "tests/unit/test_acs_loopback.py and tests/unit/test_cloud_write_refusal.py."
fi
