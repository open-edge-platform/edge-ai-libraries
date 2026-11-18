#!/usr/bin/env bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  cat <<'EOF'
Usage: pools.sh <operation> [library-name-or-id] [arguments]

Operations:
  create <library-name-or-id> <json|@file>
  read [library-name-or-id] [pool-name-or-id]       Read all pools when omitted
  sources [library-name-or-id] [pool-name-or-id]    Read attached sources
  assets [library-name-or-id] [pool-name-or-id]     Read asset ids
  update <library-ref> <pool-ref> <json|@file>      Replace attached sources
  add-sources <library-ref> <pool-ref> <source-ref>... [--replaces <source-ref>]
                                                    Add sources without detaching existing ones;
                                                    with --replaces, the one new source takes
                                                    over from the named one once it catches up
  remove-sources <library-ref> <pool-ref> <source-ref>... Detach sources, keeping the rest
  routing <library-ref> <pool-ref>                  Which source takes each kind of content
  add-assets <library-ref> <pool-ref> <json|@file>  Add assets by id or name
  graph <library-ref> <pool-ref> [limit]            The pool's concept graph (nodes, edges)
  delete <library-name-or-id> <pool-name-or-id>

Create example: ./pools.sh create docs @example/pool.json
Sources from all pools: ./pools.sh sources
Sources filtered by library or pool: ./pools.sh sources docs
Sources example: ./pools.sh sources docs default
Assets from all pools: ./pools.sh assets
Assets filtered by library or pool: ./pools.sh assets docs
Assets example: ./pools.sh assets docs default
Update example (replaces the attached source list):
  ./pools.sh update docs default '{"sources":["SOURCE_ID"]}'
Add sources example:
  ./pools.sh add-sources docs default SOURCE_ID [SOURCE_ID...]
Remove sources example (a pool keeps at least one source):
  ./pools.sh remove-sources docs default SOURCE_ID
Graph example (OKF concepts and links of the pool's graph source):
  ./pools.sh graph docs default 500
Replace a source (upgrade a model or its parameters):
  ./pools.sh add-sources docs default NEW_SOURCE_ID --replaces SOURCE_ID
Create/update `sources` and add-assets `asset_ids` accept ids or names.
Assets body: {"asset_ids":["asset-name-or-id"]}

When a library is supplied, a second filter identifies a pool by id or name.
EOF
}

pool_sources() {
  local payload="$1" library_key="${2-}" pool_key="${3-}"
  jq --arg library_key "$library_key" --arg pool_key "$pool_key" '
    [
      .[] as $library
      | select(
          $library_key == ""
          or $library.id == $library_key
          or $library.name == $library_key
        )
      | $library.asset_pools[]
      | select($pool_key == "" or .id == $pool_key or .name == $pool_key) as $pool
      | [$pool.source_statuses[].source_id] as $source_ids
      | $library.sources[]
      | select(.id as $id | $source_ids | index($id))
    ]
    | unique_by(.id)
  ' <<<"$payload"
}

pool_assets() {
  local payload="$1" library_key="${2-}" pool_key="${3-}"
  jq --arg library_key "$library_key" --arg pool_key "$pool_key" '
    [
      .[] as $library
      | select(
          $library_key == ""
          or $library.id == $library_key
          or $library.name == $library_key
        )
      | $library.asset_pools[]
      | select($pool_key == "" or .id == $pool_key or .name == $pool_key)
      | .asset_ids[]
    ]
    | unique
  ' <<<"$payload"
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
esac

operation="$1"
shift

case "$operation" in
  create)
    [[ $# -eq 2 ]] || usage_error "Usage: pools.sh create <library-name-or-id> <json|@file>"
    library_id="$(resolve_library_ref "$1")"
    library_path="$ASSET_LIBRARIES/$(urlencode "$library_id")"
    body="$(read_json_body "$2")"
    sources="$(api GET "$library_path/sources")"
    body="$(resolve_body_ref_array "$body" sources "$sources" Source)"
    api POST "$library_path/asset_pools" "$body"
    ;;
  read)
    [[ $# -le 2 ]] || usage_error "Usage: pools.sh read [library-name-or-id] [pool-name-or-id]"
    if [[ $# -eq 0 ]]; then
      api GET "$ASSET_LIBRARIES" | jq '[.[] | .asset_pools[]]'
    else
      library_id="$(resolve_library_ref "$1")"
      path="$ASSET_LIBRARIES/$(urlencode "$library_id")/asset_pools"
      if [[ $# -eq 2 ]]; then
        pool_id="$(resolve_pool_ref "$library_id" "$2")"
        path="$path/$(urlencode "$pool_id")"
      fi
      api GET "$path"
    fi
    ;;
  sources)
    [[ $# -le 2 ]] || usage_error "Usage: pools.sh sources [library-name-or-id] [pool-name-or-id]"
    if [[ $# -eq 2 ]]; then
      library_id="$(resolve_library_ref "$1")"
      pool_id="$(resolve_pool_ref "$library_id" "$2")"
      api GET "$ASSET_LIBRARIES/$(urlencode "$library_id")/asset_pools/$(urlencode "$pool_id")/sources"
    else
      payload="$(api GET "$ASSET_LIBRARIES")"
      if [[ $# -eq 0 ]]; then
        pool_sources "$payload"
      else
        library_id="$(resolve_object_ref "$payload" "$1" Library)"
        pool_sources "$payload" "$library_id"
      fi
    fi
    ;;
  assets)
    [[ $# -le 2 ]] || usage_error "Usage: pools.sh assets [library-name-or-id] [pool-name-or-id]"
    if [[ $# -eq 2 ]]; then
      library_id="$(resolve_library_ref "$1")"
      pool_id="$(resolve_pool_ref "$library_id" "$2")"
      api GET "$ASSET_LIBRARIES/$(urlencode "$library_id")/asset_pools/$(urlencode "$pool_id")/assets"
    else
      payload="$(api GET "$ASSET_LIBRARIES")"
      if [[ $# -eq 0 ]]; then
        pool_assets "$payload"
      else
        library_id="$(resolve_object_ref "$payload" "$1" Library)"
        pool_assets "$payload" "$library_id"
      fi
    fi
    ;;
  update|set-sources)
    [[ $# -eq 3 ]] || usage_error "Usage: pools.sh update <library-ref> <pool-ref> <json|@file>"
    library_id="$(resolve_library_ref "$1")"
    pool_id="$(resolve_pool_ref "$library_id" "$2")"
    library_path="$ASSET_LIBRARIES/$(urlencode "$library_id")"
    body="$(read_json_body "$3")"
    sources="$(api GET "$library_path/sources")"
    body="$(resolve_body_ref_array "$body" sources "$sources" Source)"
    api PUT "$library_path/asset_pools/$(urlencode "$pool_id")/sources" "$body"
    ;;
  add-source|add-sources)
    [[ $# -ge 3 ]] || usage_error "Usage: pools.sh add-sources <library-ref> <pool-ref> <source-ref>... [--replaces <source-ref>]"
    library_id="$(resolve_library_ref "$1")"
    pool_id="$(resolve_pool_ref "$library_id" "$2")"
    shift 2
    replaces_ref=""
    refs=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --replaces)
          [[ $# -ge 2 ]] || usage_error "--replaces needs a source name or id"
          replaces_ref="$2"
          shift 2
          ;;
        *)
          refs+=("$1")
          shift
          ;;
      esac
    done
    [[ ${#refs[@]} -ge 1 ]] || usage_error "Name at least one source to add"
    if [[ -n "$replaces_ref" && ${#refs[@]} -ne 1 ]]; then
      usage_error "--replaces applies to exactly one new source"
    fi
    library_path="$ASSET_LIBRARIES/$(urlencode "$library_id")"
    source_objects="$(api GET "$library_path/sources")"
    requested="$(jq -cn --args '$ARGS.positional' -- "${refs[@]}")"
    requested="$(resolve_object_refs "$source_objects" "$requested" Source)"
    replaces_id=""
    if [[ -n "$replaces_ref" ]]; then
      replaces_id="$(resolve_source_ref "$library_id" "$replaces_ref")"
    fi
    current_sources="$(api GET "$library_path/asset_pools/$(urlencode "$pool_id")/sources")"
    body="$(
      jq -cn --argjson current "$current_sources" --argjson requested "$requested" \
        --arg replaces "$replaces_id" '
        {sources: (
          ([$current[].id | select(. as $id | $requested | index($id) | not)] | unique)
          + (if $replaces == "" then $requested
             else [{source_id: $requested[0], replaces: $replaces}] end)
        )}'
    )"
    api PUT "$library_path/asset_pools/$(urlencode "$pool_id")/sources" "$body"
    ;;
  remove-source|remove-sources)
    [[ $# -ge 3 ]] || usage_error "Usage: pools.sh remove-sources <library-ref> <pool-ref> <source-ref>..."
    library_id="$(resolve_library_ref "$1")"
    pool_id="$(resolve_pool_ref "$library_id" "$2")"
    shift 2
    library_path="$ASSET_LIBRARIES/$(urlencode "$library_id")"
    source_objects="$(api GET "$library_path/sources")"
    requested="$(jq -cn --args '$ARGS.positional' -- "$@")"
    requested="$(resolve_object_refs "$source_objects" "$requested" Source)"
    current_sources="$(api GET "$library_path/asset_pools/$(urlencode "$pool_id")/sources")"
    body="$(
      jq -cn --argjson current "$current_sources" --argjson requested "$requested" \
        '{sources: [$current[].id | select(. as $id | $requested | index($id) | not)]}'
    )"
    [[ "$(jq '.sources | length' <<<"$body")" -gt 0 ]] \
      || usage_error "A pool needs at least one source; delete the pool instead"
    api PUT "$library_path/asset_pools/$(urlencode "$pool_id")/sources" "$body"
    ;;
  graph)
    [[ $# -ge 2 && $# -le 3 ]] || usage_error "Usage: pools.sh graph <library-ref> <pool-ref> [limit]"
    library_id="$(resolve_library_ref "$1")"
    pool_id="$(resolve_pool_ref "$library_id" "$2")"
    path="$ASSET_LIBRARIES/$(urlencode "$library_id")/asset_pools/$(urlencode "$pool_id")/graph"
    [[ $# -lt 3 ]] || path="$path?limit=$3"
    api GET "$path"
    ;;
  routing)
    [[ $# -eq 2 ]] || usage_error "Usage: pools.sh routing <library-ref> <pool-ref>"
    library_id="$(resolve_library_ref "$1")"
    pool_id="$(resolve_pool_ref "$library_id" "$2")"
    api GET "$ASSET_LIBRARIES/$(urlencode "$library_id")/asset_pools/$(urlencode "$pool_id")/routing"
    ;;
  add-assets)
    [[ $# -eq 3 ]] || usage_error "Usage: pools.sh add-assets <library-ref> <pool-ref> <json|@file>"
    library_id="$(resolve_library_ref "$1")"
    pool_id="$(resolve_pool_ref "$library_id" "$2")"
    library_path="$ASSET_LIBRARIES/$(urlencode "$library_id")"
    body="$(read_json_body "$3")"
    asset_payload="$(api GET "$library_path/assets?page_num=1&page_size=1000000")"
    body="$(resolve_body_ref_array "$body" asset_ids "$(jq -c '.assets' <<<"$asset_payload")" Asset)"
    api POST "$library_path/asset_pools/$(urlencode "$pool_id")/assets" "$body"
    ;;
  delete)
    [[ $# -eq 2 ]] || usage_error "Usage: pools.sh delete <library-name-or-id> <pool-name-or-id>"
    library_id="$(resolve_library_ref "$1")"
    pool_id="$(resolve_pool_ref "$library_id" "$2")"
    api DELETE "$ASSET_LIBRARIES/$(urlencode "$library_id")/asset_pools/$(urlencode "$pool_id")"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
