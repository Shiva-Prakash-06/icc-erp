#!/usr/bin/env bash
set -euo pipefail

bash scripts/run-e2e-server.sh >test-results/lighthouse-server.log 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT

for _ in $(seq 1 120); do
  if curl --fail --silent http://127.0.0.1:5010/healthz >/dev/null; then
    node scripts/run-lighthouse.mjs
    exit
  fi
  sleep 1
done

echo "Acceptance server did not become ready" >&2
exit 1
