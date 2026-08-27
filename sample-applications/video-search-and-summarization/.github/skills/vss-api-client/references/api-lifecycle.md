# VSS API lifecycle reference

Sources verified against `docs/user-guide/_assets/vss-api.yaml`, Pipeline Manager NestJS controllers, `pipeline-manager/src/sockets/events.gateway.ts`, event enums, nginx compose/config, and `search-ms/server.py`.

## Base URLs

| Service | Default URL | Notes |
| --- | --- | --- |
| Pipeline Manager via nginx | `http://<HOST_IP>:12345/manager` | External default. Prefix `/manager` is stripped by nginx before forwarding to Pipeline Manager. |
| Pipeline Manager direct | `http://<HOST_IP>:3001` | Host port from `PM_HOST_PORT`; internal service listens on `3000`. |
| Socket.IO via nginx | `http://<HOST_IP>:12345`, path `/ws/` | Gateway is configured with `path: '/ws/'`; clients emit `join` with a state/room ID. |
| Search microservice direct | `http://<HOST_IP>:7890` | FastAPI service, internal port `8000`. |

## Upload video

### `POST /videos`

Through nginx: `POST /manager/videos`.

Content type: `multipart/form-data`.

Fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `video` | file | yes | Controller expects field name `video`; uploaded MP4 must be streamable or returns 422. |
| `name` | string | no | Present in OpenAPI schema, but controller uses the stored filename/original name. |
| `tags` | string | no | Comma-separated string, split/trimmed into an array. |

Example:

```bash
curl -X POST http://localhost:12345/manager/videos \
  -F 'video=@./sample.mp4' \
  -F 'tags=demo,api'
```

Typical response:

```json
{"videoId":"0f7e..."}
```

Related reads:

- `GET /videos` (`/manager/videos`) returns `{ "videos": [ ... ] }`.
- `GET /videos/{videoId}` returns `{ "video": { "videoId", "name", "url", "tags", "createdAt", "updatedAt", ... } }` or 404.

## Start summarization

### `POST /summary`

Through nginx: `POST /manager/summary`.

Required JSON body:

```json
{
  "videoId": "<videoId>",
  "title": "Programmatic summary",
  "sampling": {
    "chunkDuration": 30,
    "samplingFrame": 4,
    "frameOverlap": 1,
    "multiFrame": 5
  },
  "evam": {
    "evamPipeline": "video_ingestion"
  }
}
```

Key fields:

| Field | Required | Notes |
| --- | --- | --- |
| `videoId` | yes | Must refer to an uploaded video. |
| `title` | yes | Missing title returns 400. |
| `sampling.chunkDuration` | yes | Chunk duration in seconds. |
| `sampling.samplingFrame` | yes | Number of sampled frames per chunk. |
| `sampling.frameOverlap` | yes | Frame overlap count. |
| `sampling.multiFrame` | yes | Must equal `frameOverlap + samplingFrame`; must not exceed configured maximum. |
| `evam.evamPipeline` | yes | Enum: `video_ingestion` or `object_detection`. |
| `prompts.*` | no | Optional frame/summary/audio prompt overrides. |
| `audio.audioModel` | no | Optional transcription model ID. `useFullTranscriptSummary` optional. |
| `produceFinalSummary` | no | Optional boolean; controls final map-reduce summary. |

Response (`201`):

```json
{"summaryPipelineId":"<stateId>"}
```

The returned `summaryPipelineId` is the summary state ID, the Socket.IO room name, and the path parameter for summary retrieval.

## Fetch summaries

### `GET /summary/{stateId}`

Through nginx: `GET /manager/summary/{stateId}`. Returns a UI-friendly state or `null` if absent.

Representative response shape:

```json
{
  "stateId": "<stateId>",
  "title": "Programmatic summary",
  "videoId": "<videoId>",
  "summary": "Final summary text when ready",
  "chunks": [],
  "frames": [],
  "frameSummaries": [],
  "chunkingStatus": "complete",
  "videoChunkingStatus": "complete",
  "videoSummaryStatus": "complete",
  "frameSummaryStatus": {"complete": 3, "inProgress": 0, "na": 0, "ready": 0},
  "systemConfig": {},
  "inferenceConfig": {}
}
```

Status values are `na`, `ready`, `inProgress`, and `complete`.

### `GET /summary/{stateId}/raw`

Through nginx: `GET /manager/summary/{stateId}/raw`. Returns raw persisted state, including `status.dataStoreUpload`, `status.summarizing`, `status.chunking`, `status.videoChunking`, `video`, `chunks`, `frames`, `frameSummaries`, and optional `audio`.

### Other summary endpoints

- `GET /summary` returns all raw summary states.
- `GET /summary/ui` returns all states in UI-friendly format.
- `DELETE /summary/{stateId}` deletes a state and returns `{ "message": "State deleted successfully" }`.

## Socket.IO progress events

Gateway configuration: `path: '/ws/'`, CORS `*`. Through nginx, connect to the app origin (`http://localhost:12345`) with Socket.IO path `/ws/`.

Client-to-server event:

| Event | Payload | Purpose |
| --- | --- | --- |
| `join` | `stateId` string | Joins the room named by the summary state ID. Required before state-specific summary events are received. |

Server-to-client events:

| Event | Payload source/shape | Purpose |
| --- | --- | --- |
| `summary:sync/{stateId}` | UI state | Full UI state sync. |
| `summary:sync/{stateId}/status` | UI status object | Chunking, video chunking, frame summary, video summary, and optional audio statuses. |
| `summary:sync/{stateId}/chunks` | `{ "chunks": [...], "frames": [...] }` | Chunk/frame metadata after chunking. |
| `summary:sync/{stateId}/frameSummary` | `{ "stateId", "summary", "frames", "frameKey", "startFrame", "endFrame", "status", ... }` | Per-frame/chunk caption/summary update. |
| `summary:sync/{stateId}/inferenceConfig` | inference config object | Model/device/pipeline info. |
| `summary:sync/{stateId}/summary` | `{ "stateId", "summary" }` | Final or accumulated summary text. |
| `summary:sync/{stateId}/summaryStream` | string chunk | Streaming summary chunk from `pipeline.summary.stream`. |
| `search:sync` | none | Search notification. |
| `search:update` | SearchQuery object | Managed search query state/results update. |

Internal event enum names include `socket.stateSync`, `socket.state.status`, `socket.state.chunking`, `socket.frame.summary`, `socket.state.config`, `socket.summary`, `socket.search.notification`, and `socket.search.update`; clients listen to the public Socket.IO names above, not the internal enum strings.

## Search through Pipeline Manager

Search must be enabled (`--search`, `--summary --search`, or `--summary-and-search`). Two modes are available through Pipeline Manager; a third path bypasses it entirely.

| | One-off `POST /search/query` | Managed `POST /search` |
| --- | --- | --- |
| Persistence | Not saved; result returned and discarded | Saved to Postgres; retrievable by `queryId` |
| `tags` | Accepted in DTO, **not forwarded** to search-ms | Stored as `string[]`, **forwarded** on every run/refetch |
| `timeFilter` | `value`+`unit` normalized → forwarded; `start`/`end`/`source` accepted but **not forwarded** | `value`+`unit` normalized; computed `start`/`end` stored and forwarded on every run/refetch |
| Watch/Refetch | Not supported | `PATCH /{queryId}/watch`, `POST /{queryId}/refetch` |
| Socket event | None | `search:update` emitted after each run |

### `TimeFilterSelection`: flat object (both Pipeline Manager endpoints)

The OpenAPI spec shows a nested shape - ignore it. The actual NestJS model is flat:

| Field | Type | Notes |
| --- | --- | --- |
| `value` | number | Relative lookback amount (e.g. `24`). Must be paired with `unit`. |
| `unit` | string | `"minutes"` \| `"hours"` \| `"days"` \| `"weeks"`. Must be paired with `value`. |
| `start` | ISO 8601 string | Absolute start. Stored by managed search; **not forwarded** by one-off endpoint. |
| `end` | ISO 8601 string | Absolute end. Same behaviour as `start`. |
| `source` | string | Label only (`"quick"`, `"relative"`). Stored; never sent to search-ms. |

`normalizeTimeFilter()` converts `value`+`unit` into computed `start`/`end` ISO timestamps sent to search-ms. If either is missing or invalid, **no time filter is forwarded**.

---

## One-off search: `POST /search/query`

Through nginx: `POST /manager/search/query`. Result returned immediately; nothing persisted.

### Request body (`SearchQueryDTO`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `query` | string | **yes** | Natural-language search text. |
| `tags` | string | no | Comma-separated (e.g. `"outdoor,night"`). Accepted, **not forwarded** - no tag filtering on this path. Use managed `POST /search` or direct search-ms for tag filtering. |
| `timeFilter` | object | no | Only `value`+`unit` produce a forwarded range. `start`, `end`, `source` are accepted but ignored here. |

### Examples

```bash
# Minimal
curl -sS -X POST http://localhost:12345/manager/search/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "person walking"}' | python3 -m json.tool

# All fields (tags and source are accepted but silently ignored)
curl -sS -X POST http://localhost:12345/manager/search/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"car parked at intersection","tags":"outdoor,night","timeFilter":{"value":24,"unit":"hours","source":"quick"}}' \
  | python3 -m json.tool
```

### Response (`200 OK`)

```json
{
  "results": [{
    "query_id": "<server-generated-uuid>",
    "results": [{
      "id": null,
      "metadata": {
        "video_id": "<videoId>", "video_url": "http://...", "video_path": "...",
        "segment_start": 0, "segment_end": 30,
        "timestamp": 12.3, "seek_timestamp": 12.3, "relevance_score": 0.82,
        "tags": "outdoor,night", "created_at": "2026-06-01T00:00:00Z",
        "fps": 30.0, "clip_duration": 30, "frames_in_clip": 900,
        "total_frames": 3600, "rank": 1, "aggregated": true
      },
      "page_content": "Video segment from 0s to 30s, seeking to 12.3s",
      "type": "Document", "frame_scores": []
    }],
    "aggregation_stats": {
      "total_frame_matches": 8, "segments_created": 3,
      "segments_after_filtering": 2, "final_results": 1,
      "processing_time_ms": 14.2, "segmentation_time_ms": 1.1,
      "scoring_time_ms": 0.6, "filtering_time_ms": 0.3, "formatting_time_ms": 0.2
    }
  }]
}
```

Key fields: `metadata.video_id` matches `POST /videos` response; `segment_start`/`segment_end` are boundaries in seconds; `seek_timestamp` is the best seek point; `relevance_score` is cosine similarity (higher = more relevant). `aggregation_stats` counts raw frame hits → segments → filtered segments → final results, with per-step timing in ms. Alternative shapes: `{"aggregation_enabled":false,"frame_count":N}` or `{"aggregation_failed":true,"error":"...","fallback_frame_count":N}`.

---

## Managed/persistent search: `POST /search`

Through nginx: `POST /manager/search`. Saves a `SearchQuery` to Postgres, runs immediately, returns the initial state. Supports polling, watch mode, and refetch.

### Request body (`SearchQueryDTO`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `query` | string | **yes** | Stored and forwarded to search-ms on every run. |
| `tags` | string | no | Comma-separated. Split → `string[]`, stored, **forwarded** on every run/refetch; OR-matched server-side. |
| `timeFilter` | object | no | `value`+`unit` normalized to `start`/`end`, stored in DB, forwarded on every run/refetch. `source` stored as label only. |

### Example

```bash
curl -sS -X POST http://localhost:12345/manager/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"person walking near a vehicle","tags":"outdoor,daytime","timeFilter":{"value":7,"unit":"days","source":"quick"}}' \
  | python3 -m json.tool
```

### Response (`201 Created`)

```json
{
  "queryId": "3f4a...", "query": "person walking near a vehicle",
  "watch": false, "results": [], "queryStatus": "running",
  "tags": ["outdoor", "daytime"],
  "timeFilter": {"value":7,"unit":"days","start":"2026-06-16T...","end":"2026-06-23T...","source":"quick"},
  "createdAt": "2026-06-23T17:22:05Z", "updatedAt": "2026-06-23T17:22:05Z"
}
```

`queryStatus`: `"running"` → in progress | `"idle"` → results ready | `"error"` → failed (`errorMessage` field set). `tags` is always `string[]` in the response; `timeFilter` has computed `start`/`end` added.

### Poll, watch, refetch

```bash
QUERY_ID="3f4a..."

# Poll until idle/error
while true; do
  S=$(curl -sS "http://localhost:12345/manager/search/$QUERY_ID" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["queryStatus"])')
  [ "$S" = "idle" ] || [ "$S" = "error" ] && break; sleep 2
done
curl -sS "http://localhost:12345/manager/search/$QUERY_ID" | python3 -m json.tool

# Watch mode (reruns automatically when new embeddings arrive; emits search:update over Socket.IO)
curl -sS -X PATCH "http://localhost:12345/manager/search/$QUERY_ID/watch" \
  -H 'Content-Type: application/json' -d '{"watch": true}'

# Refetch with stored filter
curl -sS -X POST "http://localhost:12345/manager/search/$QUERY_ID/refetch"

# Refetch with new time filter (updates stored filter)
curl -sS -X POST "http://localhost:12345/manager/search/$QUERY_ID/refetch" \
  -H 'Content-Type: application/json' -d '{"timeFilter":{"value":48,"unit":"hours"}}'
```

Other endpoints: `GET /manager/search` (all queries), `GET /manager/search/watched`, `GET /manager/search/{queryId}`, `DELETE /manager/search/{queryId}`.

---

## Direct search microservice

Bypasses Pipeline Manager. Use when you need tag filtering on a one-off query or explicit absolute date ranges.

Base URL: `http://<HOST_IP>:7890`. Body is a **list** of `QueryRequest` objects.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `query_id` | string | **yes** | Client-supplied; echoed in response. |
| `query` | string | **yes** | Search text. If `time_filter` is omitted, NLP parsing may derive a range from query text. |
| `tags` | string[] | no | OR-matched server-side against result metadata. |
| `time_filter.start` | ISO 8601 | required if `time_filter` present | Absolute range start; suppresses NLP time parsing. |
| `time_filter.end` | ISO 8601 | required if `time_filter` present | Absolute range end. |

```bash
# Minimal
curl -sS -X POST http://localhost:7890/query \
  -H 'Content-Type: application/json' \
  -d '[{"query_id":"q1","query":"person walking"}]'

# With tags and absolute time range
curl -sS -X POST http://localhost:7890/query \
  -H 'Content-Type: application/json' \
  -d '[{"query_id":"q1","query":"car parked at intersection","tags":["outdoor","night"],"time_filter":{"start":"2026-06-01T00:00:00Z","end":"2026-06-23T23:59:59Z"}}]' \
  | python3 -m json.tool
```

Response: same `{ "results": [ { "query_id", "results", "aggregation_stats" } ] }` structure; `query_id` echoes the client-supplied value.

Other endpoints: `GET /health` → `{"status":"ok","timestamp":"..."}`, `GET /watcher-last-updated`, `GET /initial-upload-status`.

---

## Search embeddings for uploaded video

### `POST /videos/search-embeddings/{videoId}`

Through nginx: `POST /manager/videos/search-embeddings/{videoId}`. Requires search feature to be on. Starts embedding creation for an already uploaded video and returns the downstream response when `status` is `success`; otherwise the controller raises 422.

Example:

```bash
curl -X POST http://localhost:12345/manager/videos/search-embeddings/$VIDEO_ID
```
