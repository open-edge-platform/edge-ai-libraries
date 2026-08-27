#!/usr/bin/env bash
set -u -o pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
APP_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
VIDEO_PATH=${1:-${VIDEO_PATH:-}}
API_BASE=${2:-${VSS_API_BASE:-http://localhost:12345/manager}}
TIMEOUT=${VSS_TIMEOUT_SECONDS:-1800}
INTERVAL=${VSS_POLL_INTERVAL_SECONDS:-5}
CHUNK_DURATION=${VSS_CHUNK_DURATION:-10}
SAMPLING_FRAME=${VSS_SAMPLING_FRAME:-5}
FRAME_OVERLAP=${VSS_FRAME_OVERLAP:-0}
MULTI_FRAME=${VSS_MULTI_FRAME:-$((SAMPLING_FRAME + FRAME_OVERLAP))}
EVAM_PIPELINE=${VSS_EVAM_PIPELINE:-object_detection}
TITLE=${VSS_SUMMARY_TITLE:-VSS smoke summary}
TAGS=${VSS_TAGS:-vss-smoke,summary}

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

json_len() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); path=sys.argv[1].split("."); cur=data
for part in path:
    if part == "": continue
    if isinstance(cur, list): cur = cur[int(part)]
    else: cur = cur.get(part, [])
print(len(cur) if isinstance(cur, (list, dict, str)) else 0)' "$1"
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

need curl
need python3
VIDEO=$(pick_video)
[ -n "$VIDEO" ] || fail "no video supplied and no sample video found; pass a streamable MP4 path as arg 1"
[ -f "$VIDEO" ] || fail "video not found: $VIDEO"
API_BASE=$(normalize_api_base)

echo "VSS summary smoke"
echo "API base: $API_BASE"
echo "Video: $VIDEO"

curl -fsS --max-time 10 "$API_BASE/health" >/dev/null || fail "Pipeline Manager health check failed at $API_BASE/health"

UPLOAD_RESPONSE=$(curl -fsS -X POST "$API_BASE/videos" \
  -F "video=@${VIDEO}" \
  -F "name=$(basename "$VIDEO")" \
  -F "tags=$TAGS") || fail "video upload failed"
VIDEO_ID=$(printf '%s' "$UPLOAD_RESPONSE" | json_get videoId)
[ -n "$VIDEO_ID" ] || fail "upload response did not include videoId: $UPLOAD_RESPONSE"
echo "Uploaded videoId: $VIDEO_ID"

SUMMARY_PAYLOAD=$(python3 -c 'import json,sys
video_id,title,chunk,sampling,overlap,multi,evam = sys.argv[1:]
payload={
  "videoId": video_id,
  "title": title,
  "sampling": {
    "chunkDuration": int(chunk),
    "samplingFrame": int(sampling),
    "frameOverlap": int(overlap),
    "multiFrame": int(multi),
  },
  "evam": {"evamPipeline": evam},
}
print(json.dumps(payload))' "$VIDEO_ID" "$TITLE" "$CHUNK_DURATION" "$SAMPLING_FRAME" "$FRAME_OVERLAP" "$MULTI_FRAME" "$EVAM_PIPELINE")

SUMMARY_RESPONSE=$(curl -fsS -X POST "$API_BASE/summary" \
  -H 'Content-Type: application/json' \
  --data "$SUMMARY_PAYLOAD") || fail "starting summary pipeline failed"
STATE_ID=$(printf '%s' "$SUMMARY_RESPONSE" | json_get summaryPipelineId)
[ -n "$STATE_ID" ] || fail "summary response did not include summaryPipelineId: $SUMMARY_RESPONSE"
echo "Started stateId: $STATE_ID"

deadline=$((SECONDS + TIMEOUT))
last_status=""
while [ "$SECONDS" -lt "$deadline" ]; do
  STATUS_JSON=$(curl -fsS --max-time 30 "$API_BASE/states/$STATE_ID") || { sleep "$INTERVAL"; continue; }
  chunking=$(printf '%s' "$STATUS_JSON" | json_get chunkingStatus)
  video_summary=$(printf '%s' "$STATUS_JSON" | json_get videoSummaryStatus)
  chunks=$(printf '%s' "$STATUS_JSON" | json_len chunks)
  frame_summaries=$(printf '%s' "$STATUS_JSON" | json_len frameSummaries)
  summary=$(printf '%s' "$STATUS_JSON" | json_get summary)
  status_line="chunking=${chunking:-unknown} chunks=$chunks frameSummaries=$frame_summaries final=${video_summary:-unknown}"
  if [ "$status_line" != "$last_status" ]; then echo "$status_line"; last_status=$status_line; fi
  if [ "$chunking" = "complete" ] && [ "$chunks" -gt 0 ] && [ "$video_summary" = "complete" ] && [ -n "$summary" ]; then
    excerpt=$(printf '%s' "$summary" | tr '\n' ' ' | cut -c1-500)
    echo "PASS: summary completed for videoId=$VIDEO_ID stateId=$STATE_ID"
    echo "Summary excerpt: $excerpt"
    exit 0
  fi
  err=$(printf '%s' "$STATUS_JSON" | json_get error)
  [ -z "$err" ] || fail "summary state reported error: $err"
  sleep "$INTERVAL"
done

fail "timed out after ${TIMEOUT}s waiting for final summary; last status: ${last_status:-none}"
