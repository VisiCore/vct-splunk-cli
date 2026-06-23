#!/usr/bin/env bash
# Poll splunkd's REST management port until it answers, or fail after ~6 minutes.
# Splunk 10.x boots KV Store (MongoDB) on start, so allow a generous window.
# Expects SPLUNK_PASSWORD in the environment and a container named `splunk`.
set -euo pipefail

for _ in $(seq 1 72); do
  # Bail early with logs if the container has already died.
  if [ "$(docker inspect -f '{{.State.Running}}' splunk 2>/dev/null)" != "true" ]; then
    echo "splunk container is not running" >&2
    docker logs splunk 2>&1 | tail -100 >&2 || true
    exit 1
  fi
  if curl -ksf -u "admin:${SPLUNK_PASSWORD}" \
      https://localhost:8089/services/server/info >/dev/null; then
    echo "splunkd is up"
    exit 0
  fi
  sleep 5
done

echo "splunkd did not become ready" >&2
docker logs splunk 2>&1 | tail -100 >&2
exit 1
