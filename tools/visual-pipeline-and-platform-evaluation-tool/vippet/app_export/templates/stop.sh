#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Usage: ./stop.sh [instance_id|all]   (default: all running instances)
set -Eeuo pipefail
cd "$(dirname "$0")"
source scripts/common.sh

TARGET="${1:-all}"

require_cmd jq
require_cmd curl
check_server

stop_id() {
  local code
  code=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' -X DELETE "$API_URL/pipelines/$1")
  case "$code" in
    200) echo "Stopped $1" ;;
    404) echo "Not found: $1" ;;
    409) echo "Not running: $1" ;;
    *) echo "Failed to stop $1 (HTTP $code)" >&2 ;;
  esac
}

if [[ $TARGET == all ]]; then
  mapfile -t IDS < <(api "$API_URL/pipelines/status" |
    jq -r '.[] | select(.state == "QUEUED" or .state == "RUNNING") | .id')
  [[ ${#IDS[@]} -gt 0 ]] || echo "No running instances"
  for id in "${IDS[@]}"; do
    stop_id "$id"
  done
else
  stop_id "$TARGET"
fi
