#!/usr/bin/env bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  cat <<'EOF'
Usage: sources.sh <operation> [library-name-or-id] [arguments]

Operations:
  create <library-name-or-id> <json|@file>
  read [library-name-or-id]                         Read all sources when omitted
  update <library-name-or-id> <source-name-or-id> <json|@file>
                                                    Change name, enabled or labels only
  delete <library-name-or-id> <source-name-or-id>

Example: ./sources.sh create docs @example/source.json
Video: operator_options {"asset_types":["video"],"embedding_model":"viclip-b-fp16"}
  Alternatives: viclip-l-fp16 or cosmos-224p-fp16; see prepare-models.sh --help.
Disable (freeze, data kept): ./sources.sh update docs video-viclip-b '{"enabled":false}'
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
    [[ $# -eq 2 ]] || usage_error "Usage: sources.sh create <library-name-or-id> <json|@file>"
    library_id="$(resolve_library_ref "$1")"
    body="$(read_json_body "$2")"
    database_ref="$(jq -r '.database_id // empty' <<<"$body")"
    [[ -n "$database_ref" ]] || usage_error "Source body requires database_id"
    database_id="$(resolve_database_ref "$database_ref")"
    body="$(jq -c --arg id "$database_id" '.database_id = $id' <<<"$body")"
    api POST "$ASSET_LIBRARIES/$(urlencode "$library_id")/sources" "$body"
    ;;
  read)
    [[ $# -le 1 ]] || usage_error "Usage: sources.sh read [library-name-or-id]"
    if [[ $# -eq 0 ]]; then
      api GET "$ASSET_LIBRARIES" | jq '[.[] | .sources[]]'
    else
      library_id="$(resolve_library_ref "$1")"
      api GET "$ASSET_LIBRARIES/$(urlencode "$library_id")/sources"
    fi
    ;;
  update)
    [[ $# -eq 3 ]] || usage_error "Usage: sources.sh update <library-name-or-id> <source-name-or-id> <json|@file>"
    library_id="$(resolve_library_ref "$1")"
    source_id="$(resolve_source_ref "$library_id" "$2")"
    body="$(read_json_body "$3")"
    api PATCH "$ASSET_LIBRARIES/$(urlencode "$library_id")/sources/$(urlencode "$source_id")" "$body"
    ;;
  delete)
    [[ $# -eq 2 ]] || usage_error "Usage: sources.sh delete <library-name-or-id> <source-name-or-id>"
    library_id="$(resolve_library_ref "$1")"
    source_id="$(resolve_source_ref "$library_id" "$2")"
    api DELETE "$ASSET_LIBRARIES/$(urlencode "$library_id")/sources/$(urlencode "$source_id")"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac