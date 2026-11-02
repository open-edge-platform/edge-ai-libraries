#!/usr/bin/env bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  cat <<'EOF'
Usage: databases.sh <operation> [arguments]

Operations:
  create <json|@file>              Register a database
  read [database-name-or-id]               List registrations or get one
  update <database-name-or-id> <json|@file>
  delete <database-name-or-id>
  check <database-name-or-id>
  backends

Example: ./databases.sh create @example/database.json
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
esac

operation="$1"
shift

case "$operation" in
  create)
    [[ $# -eq 1 ]] || usage_error "Usage: databases.sh create <json|@file>"
    api POST "$ENGINE_API/databases" "$1"
    ;;
  read)
    [[ $# -le 1 ]] || usage_error "Usage: databases.sh read [database-name-or-id]"
    path="$ENGINE_API/databases"
    if [[ $# -eq 1 ]]; then
      database_id="$(resolve_database_ref "$1")"
      path="$path/$(urlencode "$database_id")"
    fi
    api GET "$path"
    ;;
  update)
    [[ $# -eq 2 ]] || usage_error "Usage: databases.sh update <database-name-or-id> <json|@file>"
    database_id="$(resolve_database_ref "$1")"
    api PATCH "$ENGINE_API/databases/$(urlencode "$database_id")" "$2"
    ;;
  delete)
    [[ $# -eq 1 ]] || usage_error "Usage: databases.sh delete <database-name-or-id>"
    database_id="$(resolve_database_ref "$1")"
    api DELETE "$ENGINE_API/databases/$(urlencode "$database_id")"
    ;;
  check)
    [[ $# -eq 1 ]] || usage_error "Usage: databases.sh check <database-name-or-id>"
    database_id="$(resolve_database_ref "$1")"
    api POST "$ENGINE_API/databases/$(urlencode "$database_id")/check"
    ;;
  backends)
    [[ $# -eq 0 ]] || usage_error "backends takes no arguments"
    api GET "$ENGINE_API/databases/backends"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac