#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Wait for the VSS Pipeline Manager to report healthy, then print key URLs.
# Usage: wait-health.sh [HOST_IP] [APP_HOST_PORT] [TIMEOUT_SECONDS]
set -euo pipefail

HOST="${1:-${HOST_IP:-localhost}}"
PORT="${2:-${APP_HOST_PORT:-12345}}"
TIMEOUT="${3:-300}"

BASE="http://${HOST}:${PORT}"
HEALTH="${BASE}/manager/health"

echo "Waiting for Pipeline Manager health at ${HEALTH} (timeout ${TIMEOUT}s)..."
deadline=$(( $(date +%s) + TIMEOUT ))
until curl -sf --max-time 5 "${HEALTH}" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "${deadline}" ]; then
    echo "TIMEOUT: ${HEALTH} did not become healthy." >&2
    echo "Inspect with: docker compose ps   and   docker compose logs <service>" >&2
    exit 1
  fi
  sleep 5
done

echo "VSS is healthy."
echo "  UI:               ${BASE}/        (dual mode: ${BASE}/summary/ and ${BASE}/search/)"
echo "  Pipeline Manager: ${BASE}/manager/docs"
echo "  Data Prep:        http://${HOST}:7890/docs   (search modes)"
echo "  Embedding server: http://${HOST}:9777/docs   (search modes)"
