#!/usr/bin/env bash
# Log in to the Dockerized Splunk and write the session key (masked) to the GitHub
# step output as `session_key`. The CLI sends it as `Authorization: Splunk <key>`
# (the simpler alternative to a JWT — no token-auth enablement, no JWT minting).
# Expects SPLUNK_PASSWORD and GITHUB_OUTPUT in the environment.
set -euo pipefail

key=$(curl -ksf https://localhost:8089/services/auth/login \
  --data-urlencode "username=admin" \
  --data-urlencode "password=${SPLUNK_PASSWORD}" \
  -d output_mode=json \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["sessionKey"])')

if [ -z "${key}" ]; then
  echo "session-key login failed; empty sessionKey" >&2
  exit 1
fi

echo "::add-mask::${key}"
echo "session_key=${key}" >>"${GITHUB_OUTPUT}"
