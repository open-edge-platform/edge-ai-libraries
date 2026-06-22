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

Search must be enabled (`--search`, `--summary --search`, or unified mode). The Pipeline Manager forwards one-off searches to the search microservice.

### Time filter shape

OpenAPI documents a nested `TimeFilterSelection`:

```json
{"type":"relative","relative":{"value":24,"unit":"hours"}}
```

The current NestJS controller model and `SearchStateService.normalizeTimeFilter()` actually use the flattened UI shape below for Pipeline Manager searches; `value` and `unit` are required for a time range to be forwarded:

```json
{"value":24,"unit":"hours","source":"quick"}
```

Pipeline Manager does not currently normalize an absolute-only `{ "start": "...", "end": "..." }` filter. Use the direct search microservice if you need explicit absolute `start`/`end`.

### `POST /search/query`

Through nginx: `POST /manager/search/query`. One-off query; not saved.

Request:

```json
{
  "query": "person walking",
  "tags": "demo,api",
  "timeFilter": {"value": 24, "unit": "hours"}
}
```

Response shape from search service:

```json
{
  "results": [
    {
      "query_id": "<uuid>",
      "results": [
        {
          "id": null,
          "metadata": {
            "video_id": "...",
            "video_url": "...",
            "timestamp": 12.3,
            "relevance_score": 0.12,
            "segment_start": 0,
            "segment_end": 30,
            "seek_timestamp": 12.3,
            "tags": "demo,api",
            "created_at": "...",
            "aggregated": true,
            "rank": 1
          },
          "page_content": "Video segment from 0s to 30s, seeking to 12.3s",
          "type": "Document",
          "frame_scores": []
        }
      ],
      "aggregation_stats": {}
    }
  ]
}
```

### Saved/managed search endpoints

- `POST /search` (`/manager/search`) creates and runs a saved query. Body is the same `SearchQueryDTO`: `{ "query": string, "tags"?: comma-separated string, "timeFilter"?: object }`. Response is a `SearchQuery` with fields like `queryId`, `query`, `watch`, `results`, `queryStatus`, `tags`, `timeFilter`, `createdAt`, and `updatedAt`.
- `GET /search` returns all saved queries.
- `GET /search/watched` returns watched queries.
- `GET /search/{queryId}` returns one saved query.
- `POST /search/{queryId}/refetch` reruns it. Optional body: `{ "timeFilter": { ... } }`.
- `PATCH /search/{queryId}/watch` with `{ "watch": true }` or `{ "watch": false }` toggles watch mode.
- `DELETE /search/{queryId}` deletes a saved query.

## Direct search microservice

### `POST /query`

Direct URL: `POST http://localhost:7890/query`. Body is a list of query requests, not a single object.

Request model:

```json
[
  {
    "query_id": "q1",
    "query": "person walking",
    "tags": ["demo", "api"],
    "time_filter": {"start": "2026-01-01T00:00:00Z", "end": "2026-12-31T23:59:59Z"}
  }
]
```

Notes:

- `query_id` and `query` are required.
- `tags` is an optional array of strings.
- `time_filter` is optional and must contain explicit `start` and `end` strings.
- If explicit `time_filter` is omitted, the service may derive a time filter from natural language in `query` via `src/utils/time_filters.py`.
- Response is `{ "results": [ { "query_id", "results", "aggregation_stats" } ] }`.

Other direct endpoints:

- `GET /health` returns `{ "status": "ok", "timestamp": "..." }`.
- `GET /watcher-last-updated` returns `{ "last_updated": ... }`.
- `GET /initial-upload-status` returns `{ "status": ... }`.

## Search embeddings for uploaded video

### `POST /videos/search-embeddings/{videoId}`

Through nginx: `POST /manager/videos/search-embeddings/{videoId}`. Requires search feature to be on. Starts embedding creation for an already uploaded video and returns the downstream response when `status` is `success`; otherwise the controller raises 422.

Example:

```bash
curl -X POST http://localhost:12345/manager/videos/search-embeddings/$VIDEO_ID
```
