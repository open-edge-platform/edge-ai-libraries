#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Usage: ./run.sh [fakesink|file|rtsp] [name]
# Starts a pipeline instance and prints its instance id. Outputs are named
# after the instance name (default: <sink>-<date>-<time>).
set -Eeuo pipefail
cd "$(dirname "$0")"
source scripts/common.sh

SINK="${1:-fakesink}"
NAME="${2:-${SINK}-$(date +%Y%m%d-%H%M%S)}"
START_TIMEOUT="${START_TIMEOUT:-60}"

require_cmd jq
require_cmd curl
[[ $NAME =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] ||
  die "Invalid name '$NAME'. Use letters, digits, '.', '_' and '-'."
check_server

PIPELINE=$(jq -r --arg sink "$SINK" '.[$sink] // empty' pipelines.json)
[[ -n $PIPELINE ]] || die "Unknown output '$SINK'. Use fakesink, file or rtsp."
PIPELINE=${PIPELINE//\{name\}/$NAME}

# gvametapublish appends to an existing file, so start every run with new ones.
while read -r EVENTS; do
  rm -f "output/${EVENTS#file-path=/output/}"
done < <(grep -o 'file-path=/output/[^ ]*\.jsonl' <<<"$PIPELINE" || true)

BODY=$(jq -n --arg p "$PIPELINE" '{pipeline: $p, validate_pipeline: true}')
RESPONSE=$(curl --noproxy '*' -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -d "$BODY" "$API_URL/pipelines")
CODE=${RESPONSE##*$'\n'}
RESPONSE=${RESPONSE%$'\n'*}
[[ $CODE == 200 ]] || die "The pipeline did not start (HTTP $CODE): $RESPONSE"
ID=$(jq -r '.instance_id' <<<"$RESPONSE")

# The server validates the pipeline before running it; wait for the verdict.
STATE=QUEUED
for ((i = 0; i < START_TIMEOUT; i++)); do
  STATUS=$(api "$API_URL/pipelines/$ID/status")
  STATE=$(jq -r '.state' <<<"$STATUS")
  [[ $STATE == QUEUED ]] || break
  sleep 1
done
if [[ $STATE == ERROR ]]; then
  die "Instance $ID failed: $(jq -r '.message' <<<"$STATUS")"
fi

{
  echo "Started '$NAME' ($SINK), instance $ID, state $STATE"
  echo "  events: output/$NAME.jsonl"
  case $SINK in
    file) echo "  video:  output/$NAME.mp4 (complete when the input video ends)" ;;
    rtsp) echo "  stream: rtsp://localhost:$RTSP_PORT/$NAME" ;;
  esac
  [[ $SINK == file ]] || echo "  The input video loops. Stop with: ./stop.sh $ID"
} >&2
echo "$ID"
