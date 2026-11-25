#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Usage: ./stop_app.sh
# Stops all pipeline instances, then removes the stack's containers.
set -Eeuo pipefail
cd "$(dirname "$0")"
source scripts/common.sh

require_cmd docker
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."

if api "$API_URL/pipelines/status" >/dev/null 2>&1; then
  ./stop.sh all
fi

docker compose down
echo "App stopped. Outputs are kept in ./output"
