#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Deploys the encoder and decoder services, fetches their live OpenAPI specs,
# and diffs them against the committed specs under docs/. Fails (non-zero
# exit) if the committed docs have drifted from the running services' API.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DOCS_DIR="docs"
WORK_DIR="$(mktemp -d)"
READY_TIMEOUT_SEC=60

cleanup() {
  echo "==> Tearing down encoder/decoder containers"
  make clean >/dev/null 2>&1 || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

echo "==> Deploying encoder and decoder"
make decoder encoder

declare -A SERVICE_PORTS=( [encoder]=8001 [decoder]=8002 )
STATUS=0

for svc in encoder decoder; do
  port="${SERVICE_PORTS[$svc]}"

  echo "==> Waiting for $svc to become ready on port $port (timeout: ${READY_TIMEOUT_SEC}s)"
  deadline=$((SECONDS + READY_TIMEOUT_SEC))
  until curl -fsS "http://localhost:${port}/healthz" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "ERROR: $svc did not become ready within ${READY_TIMEOUT_SEC}s" >&2
      exit 1
    fi
    sleep 1
  done

  live_spec="$WORK_DIR/${svc}-openapi.json"
  docs_spec="$DOCS_DIR/${svc}-openapi.json"

  echo "==> Fetching live OpenAPI spec for $svc from http://localhost:${port}/openapi.json"
  curl -fsS "http://localhost:${port}/openapi.json" -o "$live_spec"

  # Normalize formatting (ordering/whitespace are preserved by json.tool) so
  # only genuine content differences are reported.
  python3 -m json.tool "$live_spec" >"$live_spec.pretty"
  python3 -m json.tool "$docs_spec" >"$docs_spec.pretty"

  if diff -u "$docs_spec.pretty" "$live_spec.pretty"; then
    echo "OK: $svc OpenAPI spec matches $docs_spec"
  else
    echo "ERROR: $svc OpenAPI spec differs from $docs_spec" >&2
    echo "       Regenerate it with: curl -fsS http://localhost:${port}/openapi.json | python3 -m json.tool > $docs_spec" >&2
    STATUS=1
  fi
done

exit "$STATUS"
