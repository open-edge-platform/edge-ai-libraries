#!/usr/bin/env bash
set -u -o pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
APP_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
VIDEO_PATH=${1:-${VIDEO_PATH:-}}
API_BASE=${2:-${VSS_API_BASE:-http://localhost:12345/manager}}
SEARCH_BASE=${VSS_SEARCH_BASE:-}
QUERY=${VSS_QUERY:-person walking in a store aisle near shelves}
TIMEOUT=${VSS_TIMEOUT_SECONDS:-600}
INTERVAL=${VSS_POLL_INTERVAL_SECONDS:-5}
TAGS=${VSS_TAGS:-vss-smoke,search}

fail() { echo "FAIL: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"; }

json_get() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); path=sys.argv[1].split("."); cur=data
for part in path:
    if part == "": continue
    if isinstance(cur, list): cur = cur[int(part)]
    else: cur = cur.get(part)
    if cur is None: break
print("" if cur is None else cur)' "$1"
}

hit_count() {
  python3 -c 'import json,sys
data=json.load(sys.stdin)
count=0
if isinstance(data, dict) and isinstance(data.get("results"), list):
    groups=data["results"]
    if groups and isinstance(groups[0], dict) and isinstance(groups[0].get("results"), list):
        count=sum(len(g.get("results", [])) for g in groups)
    else:
        count=len(groups)
print(count)'
}

pick_video() {
  if [ -n "$VIDEO_PATH" ]; then printf '%s\n' "$VIDEO_PATH"; return; fi
  for dir in "$APP_ROOT/data" "$APP_ROOT/cli/resources" "$APP_ROOT/video-ingestion/resources/videos"; do
    if [ -d "$dir" ]; then
      local candidate
      candidate=$(find "$dir" -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.mkv' -o -iname '*.webm' \) | head -n 1)
      if [ -n "$candidate" ]; then printf '%s\n' "$candidate"; return; fi
    fi
  done
}

normalize_api_base() {
  local base=${API_BASE%/}
  if curl -fsS --max-time 5 "$base/health" >/dev/null 2>&1; then printf '%s\n' "$base"; return; fi
  if curl -fsS --max-time 5 "$base/manager/health" >/dev/null 2>&1; then printf '%s\n' "$base/manager"; return; fi
  printf '%s\n' "$base"
}

run_query() {
  local query_id="vss-smoke-$(date +%s)"
  if [ -n "$SEARCH_BASE" ]; then
    local direct=${SEARCH_BASE%/}
    local payload
    payload=$(python3 -c 'import json,sys; print(json.dumps([{"query_id": sys.argv[1], "query": sys.argv[2]}]))' "$query_id" "$QUERY")
    curl -fsS -X POST "$direct/query" -H 'Content-Type: application/json' --data "$payload"
  else
    local payload
    payload=$(python3 -c 'import json,sys; print(json.dumps({"query": sys.argv[1]}))' "$QUERY")
    curl -fsS -X POST "$API_BASE/search/query" -H 'Content-Type: application/json' --data "$payload"
  fi
}

need curl
need python3
VIDEO=$(pick_video)
[ -n "$VIDEO" ] || fail "no video supplied and no sample video found; pass a streamable MP4 path as arg 1"
[ -f "$VIDEO" ] || fail "video not found: $VIDEO"
API_BASE=$(normalize_api_base)

echo "VSS search smoke"
echo "API base: $API_BASE"
if [ -n "$SEARCH_BASE" ]; then echo "Search base: ${SEARCH_BASE%/} (direct /query)"; else echo "Search base: manager shim $API_BASE/search/query"; fi
echo "Video: $VIDEO"
echo "Query: $QUERY"

curl -fsS --max-time 10 "$API_BASE/health" >/dev/null || fail "Pipeline Manager health check failed at $API_BASE/health"

UPLOAD_RESPONSE=$(curl -fsS -X POST "$API_BASE/videos" \
  -F "video=@${VIDEO}" \
  -F "name=$(basename "$VIDEO")" \
  -F "tags=$TAGS") || fail "video upload failed"
VIDEO_ID=$(printf '%s' "$UPLOAD_RESPONSE" | json_get videoId)
[ -n "$VIDEO_ID" ] || fail "upload response did not include videoId: $UPLOAD_RESPONSE"
echo "Uploaded videoId: $VIDEO_ID"

EMBED_RESPONSE=$(curl -fsS -X POST "$API_BASE/videos/search-embeddings/$VIDEO_ID") || fail "search embedding creation failed; is search mode enabled?"
echo "Embedding response: $(printf '%s' "$EMBED_RESPONSE" | tr '\n' ' ' | cut -c1-300)"

deadline=$((SECONDS + TIMEOUT))
last_count=-1
while [ "$SECONDS" -lt "$deadline" ]; do
  RESPONSE=$(run_query) || { sleep "$INTERVAL"; continue; }
  count=$(printf '%s' "$RESPONSE" | hit_count)
  if [ "$count" != "$last_count" ]; then echo "Search hits: $count"; last_count=$count; fi
  if [ "$count" -gt 0 ]; then
    excerpt=$(printf '%s' "$RESPONSE" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(json.dumps(data)[:500])')
    echo "PASS: search returned $count hit(s) for videoId=$VIDEO_ID"
    echo "Result excerpt: $excerpt"
    exit 0
  fi
  sleep "$INTERVAL"
done

fail "timed out after ${TIMEOUT}s waiting for non-empty search results for query: $QUERY"
