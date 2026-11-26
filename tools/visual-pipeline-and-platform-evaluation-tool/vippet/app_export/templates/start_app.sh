#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Usage: ./start_app.sh [fakesink|file|rtsp [name]]
# Checks the host, starts the stack and waits for DL Streamer Pipeline Server;
# with arguments, then starts a pipeline instance through ./run.sh.
set -Eeuo pipefail
cd "$(dirname "$0")"
source scripts/common.sh

HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"

require_cmd docker
require_cmd jq
require_cmd curl
docker info >/dev/null 2>&1 ||
  die "Docker daemon is not reachable. Start Docker, or add your user to the docker group."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."

mapfile -t DEVICES < <(jq -r '.devices[]' manifest.json)
for device in "${DEVICES[@]}"; do
  if [[ $device == GPU || $device == NPU ]] && [[ -z $(render_gid) ]]; then
    die "This $device pipeline needs an Intel GPU render node (/dev/dri/renderD*), and this host has none."
  fi
  if [[ $device == NPU && ! -e /dev/accel/accel0 ]]; then
    die "This NPU pipeline needs /dev/accel/accel0. Install the Intel NPU driver."
  fi
done

port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

if [[ -z $(docker compose ps -q --status running dlstreamer-pipeline-server 2>/dev/null) ]]; then
  for var in REST_PORT RTSP_PORT; do
    if port_in_use "${!var}"; then
      die "Port ${!var} is already in use. Choose another one, e.g. $var=$((${!var} + 100)) ./start_app.sh"
    fi
  done
fi

mkdir -p output
write_env
docker compose up -d

echo "Waiting for DL Streamer Pipeline Server at $API_URL ..."
for ((i = 0; i < HEALTH_TIMEOUT / 2; i++)); do
  api "$API_URL/pipelines/status" >/dev/null 2>&1 && break
  sleep 2
done
api "$API_URL/pipelines/status" >/dev/null 2>&1 ||
  die "DL Streamer Pipeline Server did not respond within ${HEALTH_TIMEOUT}s. See: docker compose logs dlstreamer-pipeline-server"
echo "Ready. Start a pipeline with ./run.sh [fakesink|file|rtsp]"

if (($# > 0)); then
  exec ./run.sh "$@"
fi
