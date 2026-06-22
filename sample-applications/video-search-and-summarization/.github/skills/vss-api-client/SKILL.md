---
name: vss-api-client
description: Helps developers call the VSS API correctly for the video-search-and-summarization sample app, including the async upload/process/summary lifecycle and search service queries. Use when someone needs to call the VSS API, upload a video programmatically, poll for the summary, subscribe to processing progress, write an integration test against VSS, or query the search service.
---

# VSS API Client

Use this skill when writing clients or integration tests for the Video Search & Summarization (VSS) sample app. The API is asynchronous: uploading a video only creates a video record; summarization starts in a separate request; progress arrives over Socket.IO; final output is fetched from summary endpoints.

## Verified base URLs and prefixes

- Default external nginx URL: `http://<HOST_IP>:12345`
- Pipeline Manager through nginx: `http://<HOST_IP>:12345/manager`
- Pipeline Manager direct container host port: `http://<HOST_IP>:3001` (`PM_HOST_PORT`)
- Search microservice direct URL: `http://<HOST_IP>:7890` (`VS_HOST_PORT`)
- Socket.IO progress path through nginx: `http://<HOST_IP>:12345` with Socket.IO `path: /ws/`

When using nginx, REST paths are prefixed with `/manager` (for example `/manager/videos`). Direct Pipeline Manager calls omit that prefix.

## Summary lifecycle: required order

1. Check service health/features: `GET /manager/health`, optionally `GET /manager/app/features`.
2. Upload the video: `POST /manager/videos` as `multipart/form-data` field `video`; optional `tags` is comma-separated. Response contains `videoId`.
3. Start processing: `POST /manager/summary` with `videoId`, `title`, `sampling`, and `evam`. Response contains `summaryPipelineId` (the summary `stateId`).
4. Subscribe to progress with Socket.IO: connect using `path: /ws/`, emit `join` with the `summaryPipelineId`, then listen for `summary:sync/{stateId}/status`, `/chunks`, `/frameSummary`, `/inferenceConfig`, `/summary`, and `/summaryStream`.
5. Poll/fetch final summary: `GET /manager/summary/{stateId}` for UI-shaped data, or `GET /manager/summary/{stateId}/raw` for raw state. Completion usually means `videoSummaryStatus: "complete"` and/or non-empty `summary`.

Ordering matters because `/videos` does not start summarization. The `summaryPipelineId` returned by `/summary` is also the Socket.IO room name and the ID used by summary retrieval endpoints.

## Curl quick start

```bash
BASE=http://localhost:12345/manager

curl -f "$BASE/health"

VIDEO_ID=$(curl -sS -X POST "$BASE/videos" \
  -F "video=@./sample.mp4" \
  -F "tags=demo,api" | python3 -c 'import json,sys; print(json.load(sys.stdin)["videoId"])')

STATE_ID=$(curl -sS -X POST "$BASE/summary" \
  -H 'Content-Type: application/json' \
  -d "{\"videoId\":\"$VIDEO_ID\",\"title\":\"API smoke\",\"sampling\":{\"chunkDuration\":30,\"samplingFrame\":4,\"frameOverlap\":1,\"multiFrame\":5},\"evam\":{\"evamPipeline\":\"video_ingestion\"}}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["summaryPipelineId"])')

curl -sS "$BASE/summary/$STATE_ID" | python3 -m json.tool
```

## Socket.IO progress snippet (JavaScript)

```js
import { io } from "socket.io-client";

const appUrl = "http://localhost:12345";
const stateId = process.env.STATE_ID;
const socket = io(appUrl, { path: "/ws/" });

socket.on("connect", () => socket.emit("join", stateId));
for (const suffix of ["status", "chunks", "frameSummary", "inferenceConfig", "summary", "summaryStream"]) {
  socket.on(`summary:sync/${stateId}/${suffix}`, (payload) => {
    console.log(suffix, payload);
  });
}
socket.on("search:update", (query) => console.log("search update", query.queryId));
```

## Python REST snippet

```python
import json, urllib.request

base = "http://localhost:12345/manager"
body = {
    "videoId": "<videoId-from-POST-/videos>",
    "title": "Programmatic summary",
    "sampling": {"chunkDuration": 30, "samplingFrame": 4, "frameOverlap": 1, "multiFrame": 5},
    "evam": {"evamPipeline": "video_ingestion"},
}
req = urllib.request.Request(
    f"{base}/summary",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
print(json.load(urllib.request.urlopen(req)))  # {"summaryPipelineId": "..."}
```

## Search queries with time filters

Pipeline Manager one-off search:

```bash
curl -sS -X POST http://localhost:12345/manager/search/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"person walking","tags":"demo,api","timeFilter":{"value":24,"unit":"hours"}}' \
  | python3 -m json.tool
```

Managed query lifecycle:

- `POST /manager/search` creates and runs a saved query.
- `GET /manager/search/{queryId}` fetches it.
- `POST /manager/search/{queryId}/refetch` reruns it, optionally with `{ "timeFilter": ... }`.
- `PATCH /manager/search/{queryId}/watch` with `{ "watch": true }` enables watch updates.
- `GET /manager/search/watched` lists watched queries.

Direct search microservice (bypasses Pipeline Manager) accepts a list at `POST http://localhost:7890/query`:

```json
[{"query_id":"q1","query":"person walking","tags":["demo"],"time_filter":{"start":"2026-01-01T00:00:00Z","end":"2026-12-31T23:59:59Z"}}]
```

## More detail

See [references/api-lifecycle.md](references/api-lifecycle.md) for endpoint schemas, response shapes, and event names. Use [scripts/api_smoke.py](scripts/api_smoke.py) for a dependency-light smoke test.
