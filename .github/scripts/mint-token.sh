#!/usr/bin/env bash
# Enable token authentication (off by default) on the Dockerized Splunk, then mint
# an admin token and write it (masked) to the GitHub step output as `token`.
# Expects SPLUNK_PASSWORD and GITHUB_OUTPUT in the environment.
#
# Robust by design: token-auth enablement can lag a moment after splunkd is up, and
# a failed mint must surface the server's response instead of feeding empty text to
# the JSON parser (which produced an opaque JSONDecodeError before).
set -euo pipefail

base="https://localhost:8089"

# Token auth is disabled by default; enable it (idempotent). No -f: we want to see
# the body if it errors rather than abort the pipeline silently.
curl -ks -u "admin:${SPLUNK_PASSWORD}" -X POST \
  "${base}/services/admin/token-auth/tokens_auth" \
  -d disabled=false >/dev/null

token=""
last=""
for _ in $(seq 1 10); do
  last=$(curl -ks -u "admin:${SPLUNK_PASSWORD}" -X POST \
    "${base}/services/authorization/tokens?output_mode=json" \
    -d name=admin -d audience=ci || true)
  token=$(printf '%s' "$last" | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
    print(data["entry"][0]["content"]["token"])
except Exception:
    pass
' 2>/dev/null || true)
  [ -n "${token}" ] && break
  sleep 3
done

if [ -z "${token}" ]; then
  echo "token mint failed; last response was:" >&2
  printf '%s\n' "${last}" >&2
  exit 1
fi

echo "::add-mask::${token}"
echo "token=${token}" >>"${GITHUB_OUTPUT}"
