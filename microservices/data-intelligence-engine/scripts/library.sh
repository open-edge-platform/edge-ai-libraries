#!/usr/bin/env bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  cat <<'EOF'
Usage: library.sh <operation> [arguments]

Operations:
  create <json|@file>
  read [library-name-or-id]
  update <library-name-or-id> <json|@file>
  delete <library-name-or-id>

Example: ./library.sh create @example/library.json
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
    [[ $# -eq 1 ]] || usage_error "Usage: library.sh create <json|@file>"
    api POST "$ASSET_LIBRARIES" "$1"
    ;;
  read)
    [[ $# -le 1 ]] || usage_error "Usage: library.sh read [library-name-or-id]"
    path="$ASSET_LIBRARIES"
    if [[ $# -eq 1 ]]; then
      library_id="$(resolve_library_ref "$1")"
      path="$path/$(urlencode "$library_id")"
    fi
    api GET "$path"
    ;;
  update)
    [[ $# -eq 2 ]] || usage_error "Usage: library.sh update <library-name-or-id> <json|@file>"
    library_id="$(resolve_library_ref "$1")"
    api PATCH "$ASSET_LIBRARIES/$(urlencode "$library_id")" "$2"
    ;;
  delete)
    [[ $# -eq 1 ]] || usage_error "Usage: library.sh delete <library-name-or-id>"
    library_id="$(resolve_library_ref "$1")"
    api DELETE "$ASSET_LIBRARIES/$(urlencode "$library_id")"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac