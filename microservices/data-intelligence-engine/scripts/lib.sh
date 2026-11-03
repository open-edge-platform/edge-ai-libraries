#!/usr/bin/env bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Shared curl helpers. Source this file; do not execute it directly.

set -euo pipefail

ENGINE_URL="${ENGINE_URL:-http://localhost:${ENGINE_PORT:-16022}}"
CURL_TIMEOUT="${CURL_TIMEOUT:-120}"
ASSET_LOOKUP_PAGE_SIZE="${ASSET_LOOKUP_PAGE_SIZE:-1000000}"
ENGINE_API="/v1"
ASSET_LIBRARIES="$ENGINE_API/libraries"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage_error() {
  printf '%s\n' "$1" >&2
  exit 2
}

require_jq() {
  command -v jq >/dev/null 2>&1 || usage_error "jq is required to format API responses"
}

urlencode() {
  require_jq
  jq -rn --arg value "$1" '$value | @uri'
}

resolve_object_ref() {
  local objects="$1" reference="$2" object_type="$3"
  local exact_id name_matches match_count

  exact_id="$(
    jq -r --arg reference "$reference" \
      '[.[] | select(.id? == $reference) | (.id // .name)][0] // empty' <<<"$objects"
  )"
  if [[ -n "$exact_id" ]]; then
    printf '%s' "$exact_id"
    return
  fi

  name_matches="$(
    jq -c --arg reference "$reference" \
      '[.[] | select(.name? == $reference) | (.id // .name)]' <<<"$objects"
  )"
  match_count="$(jq 'length' <<<"$name_matches")"
  case "$match_count" in
    1) jq -r '.[0]' <<<"$name_matches" ;;
    0) usage_error "$object_type not found: $reference" ;;
    *) usage_error "$object_type name is ambiguous: $reference; use an id" ;;
  esac
}

resolve_object_refs() {
  local objects="$1" references="$2" object_type="$3"
  local reference resolved='[]' id

  while IFS= read -r reference; do
    [[ -n "$reference" ]] || continue
    id="$(resolve_object_ref "$objects" "$reference" "$object_type")" || return $?
    resolved="$(jq -c --arg id "$id" '. + [$id] | unique' <<<"$resolved")"
  done < <(jq -r '.[]' <<<"$references")
  printf '%s' "$resolved"
}

resolve_library_ref() {
  resolve_object_ref "$(api GET "$ASSET_LIBRARIES")" "$1" "Library"
}

resolve_database_ref() {
  # A database registration's user-chosen id is also its display name.
  resolve_object_ref "$(api GET "$ENGINE_API/databases")" "$1" "Database"
}

resolve_source_ref() {
  local library_id="$1" reference="$2" path
  path="$ASSET_LIBRARIES/$(urlencode "$library_id")/sources"
  resolve_object_ref "$(api GET "$path")" "$reference" "Source"
}

resolve_pool_ref() {
  local library_id="$1" reference="$2" path
  path="$ASSET_LIBRARIES/$(urlencode "$library_id")/asset_pools"
  resolve_object_ref "$(api GET "$path")" "$reference" "Asset pool"
}

resolve_asset_ref() {
  local library_id="$1" reference="$2" path payload
  path="$ASSET_LIBRARIES/$(urlencode "$library_id")/assets?page_num=1&page_size=$ASSET_LOOKUP_PAGE_SIZE"
  payload="$(api GET "$path")"
  resolve_object_ref "$(jq -c '.assets' <<<"$payload")" "$reference" "Asset"
}

read_json_body() {
  local body="$1" body_path

  require_jq
  if [[ "$body" != @* ]]; then
    jq -c . <<<"$body" || usage_error "Invalid JSON payload"
    return
  fi

  body_path="${body#@}"
  if [[ ! -f "$body_path" ]]; then
    body_path="$SCRIPTS_DIR/$body_path"
  fi
  [[ -f "$body_path" ]] || usage_error "JSON file not found: ${body#@}"
  jq -c . "$body_path" || usage_error "Invalid JSON: $body_path"
}

resolve_body_ref_array() {
  local body="$1" field="$2" objects="$3" object_type="$4"
  local references resolved

  if ! jq -e --arg field "$field" 'has($field) and .[$field] != null' \
      >/dev/null <<<"$body"; then
    printf '%s' "$body"
    return
  fi
  references="$(jq -c --arg field "$field" '.[$field]' <<<"$body")"
  resolved="$(resolve_object_refs "$objects" "$references" "$object_type")" \
    || return $?
  jq -c --arg field "$field" --argjson resolved "$resolved" \
    '.[$field] = $resolved' <<<"$body"
}

# urlencode_path a/b c/d.pdf -> a/b%20c/d.pdf (each segment encoded, slashes kept)
urlencode_path() {
  require_jq
  jq -rn --arg value "$1" '$value | split("/") | map(@uri) | join("/")'
}

# upload_file LIBRARY_ID LOCAL_FILE RELATIVE_PATH
# PUT the file's bytes to /libraries/{id}/uploads/{path}; prints the UploadResult.
upload_file() {
  local library_id="$1" local_file="$2" relative="$3"
  curl --silent --show-error --fail-with-body --max-time "$CURL_TIMEOUT" \
    --request PUT --header 'Content-Type: application/octet-stream' \
    --upload-file "$local_file" \
    "$ENGINE_URL$ASSET_LIBRARIES/$(urlencode "$library_id")/uploads/$(urlencode_path "$relative")"
}

# upload_path LIBRARY_ID LOCAL_PATH
# Upload a file, or a folder with its structure (hidden entries skipped), and
# print the one name `file_paths` should carry for it: the file's upload name,
# or the folder's -- which the engine ingests as an OKF bundle or expands into
# its supported files. Progress goes to stderr.
upload_path() {
  local library_id="$1" local_path="$2" base name="" result file relative inner
  local_path="$(realpath "$local_path")"
  base="$(basename "$local_path")"
  if [[ -f "$local_path" ]]; then
    result="$(upload_file "$library_id" "$local_path" "$base")" || {
      printf '%s\n' "$result" >&2; return 1; }
    printf 'Uploaded %s\n' "$local_path" >&2
    jq -r '.name' <<<"$result"
    return
  fi
  [[ -d "$local_path" ]] || usage_error "Not a file or folder: $local_path"
  local count=0
  while IFS= read -r -d '' file; do
    inner="${file#"$local_path"/}"
    [[ "/$inner" == */.* ]] && continue   # hidden file or folder
    relative="$base/$inner"
    result="$(upload_file "$library_id" "$file" "$relative")" || {
      printf '%s\n' "$result" >&2; return 1; }
    # The response names the file under the library's upload folder; the
    # folder's name is that with the file's own part swapped for the folder.
    name="$(jq -r --arg rel "$relative" --arg base "$base" \
      '.name | .[0:(length - ($rel | length))] + $base' <<<"$result")"
    count=$((count + 1))
  done < <(find "$local_path" -type f -print0 | sort -z)
  [[ "$count" -gt 0 ]] || usage_error "Folder has no files to upload: $local_path"
  printf 'Uploaded %s (%d files)\n' "$local_path" "$count" >&2
  printf '%s\n' "$name"
}

# api METHOD PATH [JSON|@FILE]
# Writes a formatted response body to stdout and returns non-zero for HTTP failures.
api() {
  local method="$1" path="$2" body="${3-}"
  local body_path
  local response curl_status
  local args=(
    --silent
    --show-error
    --fail-with-body
    --request "$method"
    --header 'Accept: application/json'
    --max-time "$CURL_TIMEOUT"
  )

  if [[ "$body" == @* ]]; then
    body_path="${body#@}"
    if [[ ! -f "$body_path" ]]; then
      body_path="$SCRIPTS_DIR/$body_path"
    fi
    [[ -f "$body_path" ]] || usage_error "JSON file not found: ${body#@}"
    body="@$body_path"
  fi

  if [[ -n "$body" ]]; then
    args+=(--header 'Content-Type: application/json' --data-binary "$body")
  fi

  require_jq
  if response="$(curl "${args[@]}" "$ENGINE_URL$path")"; then
    curl_status=0
  else
    curl_status=$?
  fi

  if [[ -n "$response" ]]; then
    if jq -e . >/dev/null 2>&1 <<<"$response"; then
      jq . <<<"$response"
    else
      printf '%s\n' "$response"
    fi
  fi
  return "$curl_status"
}
