#!/usr/bin/env bash
# Enable token authentication (off by default) on the Dockerized Splunk, then mint
# an admin token and write it (masked) to the GitHub step output as `token`.
# Expects SPLUNK_PASSWORD and GITHUB_OUTPUT in the environment.
set -euo pipefail

curl -ksf -u "admin:${SPLUNK_PASSWORD}" -X POST \
  https://localhost:8089/services/admin/token-auth/tokens_auth \
  -d disabled=false >/dev/null || true

token=$(curl -ksf -u "admin:${SPLUNK_PASSWORD}" -X POST \
  https://localhost:8089/services/authorization/tokens \
  -d name=admin -d audience=ci -d output_mode=json |
  python -c 'import sys, json; print(json.load(sys.stdin)["entry"][0]["content"]["token"])')

if [ -z "${token}" ]; then
  echo "token mint failed" >&2
  exit 1
fi

echo "::add-mask::${token}"
echo "token=${token}" >>"${GITHUB_OUTPUT}"
