#!/usr/bin/env bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  cat <<'EOF'
Usage: status.sh <operation> [argument]

Operations:
  health                 Get service health
  databases              List registered databases
  backends               List supported database backends
  check <database-name-or-id>    Check one database connection
  models [type]          List all models or one model type
  model-names <type>     List model names for one type
  devices                List inference devices
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
esac

operation="$1"
shift

case "$operation" in
  health)
    [[ $# -eq 0 ]] || usage_error "health takes no arguments"
    api GET /health
    ;;
  databases)
    [[ $# -eq 0 ]] || usage_error "databases takes no arguments"
    api GET "$ENGINE_API/databases"
    ;;
  backends)
    [[ $# -eq 0 ]] || usage_error "backends takes no arguments"
    api GET "$ENGINE_API/databases/backends"
    ;;
  check)
    [[ $# -eq 1 ]] || usage_error "Usage: status.sh check <database-name-or-id>"
    database_id="$(resolve_database_ref "$1")"
    api POST "$ENGINE_API/databases/$(urlencode "$database_id")/check"
    ;;
  models)
    [[ $# -le 1 ]] || usage_error "Usage: status.sh models [type]"
    path="$ENGINE_API/models"
    [[ $# -eq 0 ]] || path="$path/$1"
    api GET "$path"
    ;;
  model-names)
    [[ $# -eq 1 ]] || usage_error "Usage: status.sh model-names <type>"
    api GET "$ENGINE_API/models/$1/names"
    ;;
  devices)
    [[ $# -eq 0 ]] || usage_error "devices takes no arguments"
    api GET "$ENGINE_API/models/devices"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac