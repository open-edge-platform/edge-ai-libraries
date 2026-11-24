#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Shared helpers, sourced by the app scripts from the app directory.

# Settings saved by start_app.sh; variables set in the environment win.
if [[ -f .env ]]; then
  while IFS='=' read -r key value; do
    [[ $key =~ ^[A-Z_][A-Z0-9_]*$ && -z ${!key:-} ]] && export "$key=$value"
  done <.env
fi

REST_PORT="${REST_PORT:-18080}"
RTSP_PORT="${RTSP_PORT:-18554}"
export REST_PORT RTSP_PORT
API_URL="http://127.0.0.1:${REST_PORT}"

die() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required. Install it and try again."
}

# The API is local, so it never goes through a proxy.
api() { curl --noproxy '*' -fsS "$@"; }

check_server() {
  api "$API_URL/pipelines/status" >/dev/null 2>&1 ||
    die "DL Streamer Pipeline Server is not reachable at $API_URL. Run ./start_app.sh first."
}

# Group that owns the GPU render node, empty when the host has none.
render_gid() {
  local node
  for node in /dev/dri/renderD*; do
    if [[ -e $node ]]; then
      stat -c %g "$node"
      return
    fi
  done
}

# Save the values compose.yml reads, so that plain `docker compose` works too.
write_env() {
  local gid
  gid=$(render_gid)
  {
    echo "APP_UID=$(id -u)"
    echo "APP_GID=$(id -g)"
    [[ -z $gid ]] || echo "RENDER_GID=$gid"
    echo "REST_PORT=$REST_PORT"
    echo "RTSP_PORT=$RTSP_PORT"
  } >.env
}
