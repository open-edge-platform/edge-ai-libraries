#!/usr/bin/env bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

RETRIEVER_TYPES="rrf vectorsimilarity bm25 graph"

prepare_retrieve_body() {
  local body="$1" libraries library_id library_path pool_refs pools resolved
  local resolved_pools="" type

  body="$(read_json_body "$body")" || return $?
  type="$(jq -r '.retriever_type // empty' <<<"$body")"
  # shellcheck disable=SC2076  # quoted on purpose: literal whole-word membership test
  if [[ -n "$type" && ! " $RETRIEVER_TYPES " =~ " $type " ]]; then
    usage_error "retriever_type must be one of: $RETRIEVER_TYPES"
  fi
  libraries="$(api GET "$ASSET_LIBRARIES")" || return $?
  body="$(resolve_body_ref_array "$body" libraries "$libraries" Library)" \
    || return $?
  if [[ "$(jq '.libraries | length' <<<"$body")" -eq 0 ]]; then
    usage_error "Retrieve body requires at least one library name or id"
  fi

  if jq -e 'has("asset_pool_ids") and (.asset_pool_ids | length > 0)' \
      >/dev/null <<<"$body"; then
    pool_refs="$(jq -c '.asset_pool_ids' <<<"$body")"
    while IFS= read -r library_id; do
      library_path="$ASSET_LIBRARIES/$(urlencode "$library_id")"
      pools="$(api GET "$library_path/asset_pools")" || return $?
      resolved="$(resolve_object_refs "$pools" "$pool_refs" "Asset pool")" \
        || return $?
      if [[ -z "$resolved_pools" ]]; then
        resolved_pools="$resolved"
      elif [[ "$resolved_pools" != "$resolved" ]]; then
        usage_error \
          "Asset pool names resolve to different ids across libraries; use ids shared by every library"
      fi
    done < <(jq -r '.libraries[]' <<<"$body")
    body="$(
      jq -c --argjson resolved "$resolved_pools" \
        '.asset_pool_ids = $resolved' <<<"$body"
    )"
  fi

  printf '%s' "$body"
}

# query LIBRARY TEXT [options] -> a RetrieveRequest body.
query_body() {
  local library="$1" text="$2" pools=() type="" top_k="" rerank="" reranker="" trace=false
  local targets="" allow_missing=false reject_requested=false media_option=false
  shift 2
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --pool) [[ $# -ge 2 ]] || usage_error "--pool needs a value"; pools+=("$2"); shift 2 ;;
      --type) [[ $# -ge 2 ]] || usage_error "--type needs a value"; type="$2"; shift 2 ;;
      --top-k) [[ $# -ge 2 ]] || usage_error "--top-k needs a value"; top_k="$2"; shift 2 ;;
      --rerank) [[ $# -ge 2 ]] || usage_error "--rerank needs a value"; rerank="$2"; shift 2 ;;
      --reranker) [[ $# -ge 2 ]] || usage_error "--reranker needs a value"; reranker="$2"; shift 2 ;;
      --target-media) [[ $# -ge 2 ]] || usage_error "--target-media needs a value"; targets="$2"; media_option=true; shift 2 ;;
      --allow-missing-targets) allow_missing=true; shift ;;
      --reject-file) [[ $# -ge 2 ]] || usage_error "--reject-file needs a value"; reject_requested=true; shift 2 ;;
      --trace) trace=true; shift ;;
      *) usage_error "Unknown option: $1" ;;
    esac
  done
  [[ -z "$top_k" || "$top_k" =~ ^[0-9]+$ ]] || usage_error "--top-k must be a number"
  [[ -z "$rerank" || "$rerank" =~ ^[0-9]+$ ]] || usage_error "--rerank must be a number"
  if [[ "$media_option" == true && ! "$targets" =~ ^(document|video|image|audio)(,(document|video|image|audio))*$ ]]; then
    usage_error "--target-media requires comma-separated document,video,image,audio values"
  fi
  if [[ -n "$targets" ]]; then
    if [[ -n "$top_k" ]] && ((10#$top_k < 1 || 10#$top_k > 100)); then usage_error "--top-k must be 1-100"; fi
    if [[ -n "$rerank" ]] && ((10#$rerank < 1)); then usage_error "--rerank must be positive"; fi
  elif [[ "$allow_missing" == true || "$reject_requested" == true ]]; then
    usage_error "--allow-missing-targets and --reject-file require --target-media"
  fi
  local targets_json='[]' target
  if [[ -n "$targets" ]]; then
    IFS=',' read -r -a target_list <<<"$targets"
    ((${#target_list[@]} > 0)) || usage_error "--target-media requires document,video,image,audio"
    declare -A seen=()
    for target in "${target_list[@]}"; do
      [[ "$target" == document || "$target" == video || "$target" == image || "$target" == audio ]] || usage_error "Invalid media target: $target"
      [[ -z "${seen[$target]:-}" ]] || usage_error "Duplicate media target: $target"
      seen[$target]=1
    done
    targets_json="$(jq -cn '$ARGS.positional' --args -- "${target_list[@]}")"
  fi
  jq -cn --arg query "$text" --arg library "$library" --arg type "$type" \
    --arg top_k "$top_k" --arg rerank "$rerank" --arg reranker "$reranker" \
    --argjson targets "$targets_json" --argjson allow_missing "$allow_missing" \
    --argjson trace "$trace" \
    --argjson pools "$(jq -cn '$ARGS.positional' --args -- ${pools[@]+"${pools[@]}"})" '
    {query: $query, libraries: [$library], asset_pool_ids: $pools}
    + (if $targets != [] then {target_media: $targets, allow_missing_targets: $allow_missing} else {} end)
    + (if $type != "" then {retriever_type: $type} else {} end)
    + (if $top_k != "" then {top_k: ($top_k | tonumber)} else {} end)
    + (if $trace or $type == "graph" then {include_graph_trace: true} else {} end)
    + (if $rerank != "" or $reranker != "" then
        {postprocess: ({processor_type: "reranker"}
          + (if $rerank != "" then {top_n: ($rerank | tonumber)} else {} end)
          + (if $reranker != "" then {reranker_model: {model_id: $reranker}} else {} end))}
      else {} end)'
}

check_media_response() {
  local response="$1" body="$2" reject_files="$3" detail
  if ! detail="$(jq -er --argjson request "$body" --argjson rejected "$reject_files" '
    def valid_hit($targets):
      type == "object" and (.id | type == "string") and (.text | type == "string")
      and (.score | type == "number") and (.score | isnan | not) and (.score | isinfinite | not)
      and (.metadata | type == "object") and (.metadata.target_media as $t | $targets | index($t) != null)
      and (.metadata.file_name as $f | $rejected | index($f) == null);
    ($request.target_media | unique) as $targets
    | ($request.postprocess.top_n // 3) as $top_n
    | if (.retrieved_chunks | type) != "array" or (.chunks | type) != "array" then
        "missing chunk arrays"
      elif ((.retrieved_chunks + .chunks) | all(.[]; valid_hit($targets))) | not then
        "invalid hit, target, score or excluded file"
      else
        # Candidates merge round-robin across (library, pool, source), so no
        # per-target ordering or count is asserted -- only shape, ranks and the
        # rerank fallback (chunks == recall order) are checked.
        .chunks as $hits
        | ($hits | length) as $count
        | ([range(0; $count) | $hits[.].metadata.rank] == [range(1; $count + 1)]) as $global
        | if $request.postprocess == null then
            if $global and ($hits == .retrieved_chunks) then "ok" else "invalid recall order or rank" end
          elif $global and (($count <= $top_n) or ($hits == .retrieved_chunks)) then "ok"
          else "invalid ranking or result count" end
      end' <<<"$response")"; then
    printf 'invalid media response: %s\n' "${detail:-malformed response}" >&2
    return 1
  fi
  if [[ "$detail" != ok ]]; then
    printf 'invalid media response: %s\n' "$detail" >&2
    return 1
  fi
}

usage() {
  cat <<'USAGE'
Usage: retrieve.sh <json|@file>
       retrieve.sh query <library> <text> [--pool <pool>]... [--type <type>]
                   [--top-k N] [--rerank N] [--reranker MODEL] [--trace]
                   [--target-media document,video,image,audio]
                   [--allow-missing-targets] [--reject-file NAME]...

Types: rrf (the default: vector + BM25 + graph, fused), vectorsimilarity, bm25,
graph. Without --pool every pool in the library is searched. --rerank N reranks to
the top N with the engine's default reranker (or --reranker MODEL). --trace adds
`graph_traces` (seeds, concepts reached, links walked) for rrf/graph; --type graph
always includes it.

--target-media scopes the search to the named modalities and may be combined
freely (document included) and with --pool/--type/--trace. top_k applies per
source; when media is involved, reranking uses the media reranker unless
--reranker names a model. The response is checked for valid chunks and excluded
file names.

In a JSON body, set `retriever_type`, `postprocess` (to rerank) and
`include_graph_trace` directly. Library and pool names are resolved to ids.
USAGE
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
esac

if [[ "$1" == "query" ]]; then
  [[ $# -ge 3 ]] || usage_error "Usage: retrieve.sh query <library> <text> [options]"
  shift
  reject_files=()
  query_args=("$@")
  for ((i=2; i<${#query_args[@]}; i++)); do
    if [[ "${query_args[i]}" == --reject-file ]]; then
      [[ $((i+1)) -lt ${#query_args[@]} ]] || usage_error "--reject-file needs a value"
      reject_files+=("${query_args[i+1]}")
      i=$((i+1))
    fi
  done
  REJECT_FILES_JSON="$(jq -cn '$ARGS.positional' --args -- "${reject_files[@]}")"
  body="$(query_body "$@")" || exit $?
else
  [[ $# -eq 1 ]] || usage_error "Usage: retrieve.sh <json|@file>"
  body="$1"
fi
body="$(prepare_retrieve_body "$body")" || exit $?
response="$(api POST "$ENGINE_API/retrieve" "$body")" || exit $?
if jq -e '(.target_media | type) == "array" and (.target_media | length) > 0' >/dev/null <<<"$body"; then
  check_media_response "$response" "$body" "${REJECT_FILES_JSON:-[]}" || exit 1
fi
printf '%s\n' "$response"
