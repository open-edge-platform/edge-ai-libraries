#!/usr/bin/env bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# A requested path as a local file or folder, or empty when it only exists on
# the engine host (then it is sent as-is and the engine resolves it).
local_path_of() {
  local requested="$1" payload_dir="$2" candidate
  for candidate in "$requested" "$SCRIPTS_DIR/$requested" "$payload_dir/$requested"; do
    if [[ -e "$candidate" ]]; then
      realpath "$candidate"
      return
    fi
  done
}

# Upload every local `file_paths` entry through the API and swap in the name it
# was stored under; resolve `asset_pool_ids` names to ids.
prepare_create_body() {
  local library_id="$1" body="$2" payload payload_path="" payload_dir="$PWD"
  local requested local_path name pool_objects

  require_jq
  if [[ "$body" == @* ]]; then
    payload_path="${body#@}"
    [[ -f "$payload_path" ]] || payload_path="$SCRIPTS_DIR/$payload_path"
    [[ -f "$payload_path" ]] || usage_error "JSON file not found: ${body#@}"
    payload_dir="$(cd "$(dirname "$payload_path")" && pwd)"
    payload="$(jq -c . "$payload_path")" || usage_error "Invalid JSON: $payload_path"
  else
    payload="$(jq -c . <<<"$body")" || usage_error "Invalid JSON payload"
  fi

  pool_objects="$(api GET "$ASSET_LIBRARIES/$(urlencode "$library_id")/asset_pools")" || return $?
  payload="$(resolve_body_ref_array "$payload" asset_pool_ids "$pool_objects" "Asset pool")" || return $?

  while IFS= read -r requested; do
    [[ -n "$requested" ]] || continue
    local_path="$(local_path_of "$requested" "$payload_dir")"
    [[ -n "$local_path" ]] || { printf 'Using engine-side path %s\n' "$requested" >&2; continue; }
    name="$(upload_path "$library_id" "$local_path")" || return $?
    payload="$(jq -c --arg from "$requested" --arg to "$name" \
      '.file_paths |= map(if . == $from then $to else . end)' <<<"$payload")"
  done < <(jq -r '.file_paths[]? // empty' <<<"$payload")

  printf '%s' "$payload"
}

# Poll until every asset reports `ready` (or the engine stops tracking it).
wait_ready() {
  local library_id="$1" ids="$2" deadline page pending
  deadline=$(( $(date +%s) + ${WAIT_TIMEOUT:-1800} ))
  while :; do
    page="$(api GET "$ASSET_LIBRARIES/$(urlencode "$library_id")/assets?page_num=1&page_size=$ASSET_LOOKUP_PAGE_SIZE")" || return $?
    # An asset is listed only once the background ingest registers it, so a
    # missing id is still pending, not done.
    pending="$(jq -c --argjson ids "$ids" '
      (.assets | map({key: .id, value: .}) | from_entries) as $by_id
      | [$ids[] | . as $id | $by_id[$id] as $a
         | if $a == null then {name: $id, materialization: "registering"}
           elif $a.materialization != null and $a.materialization != "ready" then {name: $a.name, materialization: $a.materialization}
           else empty end]' <<<"$page")"
    if [[ "$pending" == "[]" ]]; then
      jq --argjson ids "$ids" '[.assets[] | select(.id as $id | $ids | index($id)) | {id, name, kind, asset_pool_ids, materialization}]' <<<"$page"
      return 0
    fi
    # A failed materialization will not turn ready; stop instead of waiting out the timeout.
    if jq -e 'any(.[]; .materialization == "failed")' <<<"$pending" >/dev/null; then
      printf 'Failed: %s\n' "$(jq -r 'map(select(.materialization == "failed") | .name) | join(", ")' <<<"$pending")" >&2
      return 1
    fi
    (( $(date +%s) < deadline )) || { printf 'Timed out waiting for: %s\n' "$pending" >&2; return 1; }
    printf 'Waiting: %s\n' "$(jq -r 'map("\(.name) (\(.materialization))") | join(", ")' <<<"$pending")" >&2
    sleep "${WAIT_INTERVAL:-3}"
  done
}

usage() {
  cat <<'EOF'
Usage: assets.sh <operation> <library-name-or-id> [arguments]

Operations:
  add <library> <path>... [--pool <pool>]... [--text <text>] [--wait]
                         Upload local files or folders and ingest them
  create <library> <json|@file> [--wait]
                         Same, from an AssetCreateRequest body
  upload <library> <path>...
                         Only stage files/folders; prints the names to ingest
  read <library> [page-number] [page-size]
  wait <library> <asset-name-or-id>...
                         Block until the assets finish ingesting
  delete <library> <json|@file>
  delete-one <library> <asset-name-or-id>

Local files and folders are uploaded through the engine's API, so this works
against a remote engine too. A folder keeps its structure: an OKF bundle is
ingested as one asset, any other folder as its supported files. A path that does
not exist locally is sent unchanged, as a path on the engine host.

Create body: {"file_paths":["manual.pdf","okf_bundle/"],"text":"optional","asset_pool_ids":["default"]}
Delete body: {"asset_ids":["<asset-name-or-id>"]}
Deleting removes stored content, vector chunks and, for OKF bundles, graph concepts.
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
esac

operation="$1"
shift

case "$operation" in
  add)
    [[ $# -ge 2 ]] || usage_error "Usage: assets.sh add <library> <path>... [--pool <pool>]... [--text <text>] [--wait]"
    library_ref="$1"; shift
    paths=() pools=() text="" wait=false
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --pool) [[ $# -ge 2 ]] || usage_error "--pool needs a value"; pools+=("$2"); shift 2 ;;
        --text) [[ $# -ge 2 ]] || usage_error "--text needs a value"; text="$2"; shift 2 ;;
        --wait) wait=true; shift ;;
        *) paths+=("$1"); shift ;;
      esac
    done
    [[ ${#paths[@]} -gt 0 || -n "$text" ]] || usage_error "Give at least one path or --text"
    body="$(jq -cn --args --arg text "$text" --argjson pools "$(jq -cn '$ARGS.positional' --args -- ${pools[@]+"${pools[@]}"})" \
      '{file_paths: $ARGS.positional, asset_pool_ids: $pools} + (if $text == "" then {} else {text: $text} end)' \
      -- ${paths[@]+"${paths[@]}"})"
    next=("$library_ref" "$body")
    if $wait; then next+=(--wait); fi
    set -- "${next[@]}"
    ;&
  create)
    [[ $# -ge 2 && $# -le 3 ]] || usage_error "Usage: assets.sh create <library> <json|@file> [--wait]"
    [[ $# -lt 3 || "$3" == "--wait" ]] || usage_error "Unknown option: $3"
    library_id="$(resolve_library_ref "$1")"
    body="$(prepare_create_body "$library_id" "$2")" || exit $?
    result="$(api POST "$ASSET_LIBRARIES/$(urlencode "$library_id")/assets" "$body")" || { printf '%s\n' "$result"; exit 1; }
    printf '%s\n' "$result"
    if [[ "${3:-}" == "--wait" ]]; then
      wait_ready "$library_id" "$(jq -c '.asset_ids' <<<"$result")"
    fi
    ;;
  upload)
    [[ $# -ge 2 ]] || usage_error "Usage: assets.sh upload <library> <path>..."
    library_id="$(resolve_library_ref "$1")"; shift
    names=()
    for path in "$@"; do
      [[ -e "$path" ]] || usage_error "Not a local file or folder: $path"
      names+=("$(upload_path "$library_id" "$path")") || exit $?
    done
    jq -n '{file_paths: $ARGS.positional}' --args -- "${names[@]}"
    ;;
  read)
    [[ $# -ge 1 && $# -le 3 ]] || usage_error "Usage: assets.sh read <library-name-or-id> [page-number] [page-size]"
    library_id="$(resolve_library_ref "$1")"
    page_number="${2:-1}"
    page_size="${3:-20}"
    api GET "$ASSET_LIBRARIES/$(urlencode "$library_id")/assets?page_num=$page_number&page_size=$page_size"
    ;;
  wait)
    [[ $# -ge 2 ]] || usage_error "Usage: assets.sh wait <library> <asset-name-or-id>..."
    library_id="$(resolve_library_ref "$1")"; shift
    refs="$(jq -cn '$ARGS.positional' --args -- "$@")"
    deadline=$(( $(date +%s) + ${WAIT_TIMEOUT:-1800} ))
    # Right after an ingest the background task may not have registered an
    # asset yet, so a name that is not listed is waited for, not refused.
    until page="$(api GET "$ASSET_LIBRARIES/$(urlencode "$library_id")/assets?page_num=1&page_size=$ASSET_LOOKUP_PAGE_SIZE")" \
      && ids="$(resolve_object_refs "$(jq -c '.assets' <<<"$page")" "$refs" Asset 2>/dev/null)"; do
      if (( $(date +%s) >= deadline )); then
        resolve_object_refs "$(jq -c '.assets' <<<"$page")" "$refs" Asset >/dev/null
        exit 1
      fi
      printf 'Waiting for the assets to be registered\n' >&2
      sleep "${WAIT_INTERVAL:-3}"
    done
    wait_ready "$library_id" "$ids"
    ;;
  delete)
    [[ $# -eq 2 ]] || usage_error "Usage: assets.sh delete <library-name-or-id> <json|@file>"
    library_id="$(resolve_library_ref "$1")"
    library_path="$ASSET_LIBRARIES/$(urlencode "$library_id")"
    body="$(read_json_body "$2")"
    asset_payload="$(api GET "$library_path/assets?page_num=1&page_size=$ASSET_LOOKUP_PAGE_SIZE")"
    body="$(resolve_body_ref_array "$body" asset_ids "$(jq -c '.assets' <<<"$asset_payload")" Asset)"
    api DELETE "$library_path/assets" "$body"
    ;;
  delete-one)
    [[ $# -eq 2 ]] || usage_error "Usage: assets.sh delete-one <library-name-or-id> <asset-name-or-id>"
    library_id="$(resolve_library_ref "$1")"
    asset_id="$(resolve_asset_ref "$library_id" "$2")"
    api DELETE "$ASSET_LIBRARIES/$(urlencode "$library_id")/assets/$(urlencode "$asset_id")"
    ;;
  *) usage >&2; exit 2 ;;
esac
