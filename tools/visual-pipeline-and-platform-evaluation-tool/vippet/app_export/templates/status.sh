#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Usage: ./status.sh [instance_id]   (default: all instances, as JSON)
set -Eeuo pipefail
cd "$(dirname "$0")"
source scripts/common.sh

require_cmd jq
require_cmd curl
check_server

if [[ $# -eq 0 ]]; then
  api "$API_URL/pipelines/status" | jq .
else
  api "$API_URL/pipelines/$1/status" 2>/dev/null | jq . || die "Unknown instance $1"
fi
