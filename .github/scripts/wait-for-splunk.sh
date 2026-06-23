#!/usr/bin/env bash
# Poll splunkd's REST management port until it answers, or fail after ~5 minutes.
# Expects SPLUNK_PASSWORD in the environment and a container named `splunk`.
set -euo pipefail

for _ in $(seq 1 60); do
  if curl -ksf -u "admin:${SPLUNK_PASSWORD}" \
      https://localhost:8089/services/server/info >/dev/null; then
    echo "splunkd is up"
    exit 0
  fi
  sleep 5
done

echo "splunkd did not become ready" >&2
docker logs splunk | tail -100
exit 1
