<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS MCP server reference

Sources: `mcp/src/**`, `mcp/compose.yaml`, `docker/compose.mcp.yaml`,
`pipeline-manager/src/search/**`.

## Request flow

```text
agent --Streamable HTTP--> nginx gateway http://<VSS_IP>:12345/mcp --> MCP server (:8000/mcp)
      --HTTP--> nginx gateway http://<VSS_IP>:12345/manager/... --> Pipeline Manager
```

The server calls only the gateway, never `pipeline-manager:3000`, so every URL
it hands to an agent is one it has reached itself.

## Behaviours worth knowing

- **Surface follows the deployment.** `GET /app/features` is read once at
  startup. Tools, resources and prompts for a disabled feature are never
  registered. There is no way to force the surface by hand.
- **`vss_summarize_video` returns only the final summary**, in full; with
  `final_summary=false` it returns the full timeline instead.
  `vss_get_video_summary_timeline` always returns the timeline.
- **Summaries use the VSS defaults.** `vss_summarize_video` sends
  `produceFinalSummary: true` and polls until `videoSummaryStatus` is
  `"complete"`, like the UI. Sampling (8 s chunks, 8 frames, the deployment's
  overlap), EVAM pipeline (the deployment's) and audio (on, with
  `meta.defaultAudioModel` when there is one) also match the UI, and each can
  be overridden; invalid values are rejected before `POST /summary`. With
  `final_summary=false`, `videoSummaryStatus` ends at `"na"`, so polling keys
  off chunking completion plus a drained `frameSummaryStatus`. Summary-based
  indexing (`vss_index_video`) stays chunk-only without audio. If the wait
  budget runs out, the tool returns a `state_id` for `vss_get_video_summary_timeline`.
- **Searches are persisted.** `vss_search_video` creates a query with
  `POST /search`, as the UI does, then polls `GET /search/{queryId}` until
  `queryStatus` leaves `running` (default budget 60 s, or `wait_seconds`). It
  returns `query_id` and `status`; `status: "running"` means fetch the hits
  later with `vss_get_search`, which with `refresh=true` (or `start`/`end`)
  re-runs it via `POST /search/{id}/refetch` first. `vss_list_searches` and
  `vss_watch_search` wrap `GET /search` and `PATCH /search/{id}/watch`. A failed query (`queryStatus: "error"`) is
  returned as a tool error.
- **Watching is tracking.** `vss_watch_search` can create the search itself
  (`query`, `image`, or `from_hit`, which fetches the hit's crop with
  `GET /frames` and searches by it), with `window_minutes` as a relative
  `timeFilter` that Pipeline Manager recomputes on every refresh. Polls read
  `GET /search/{id}` and return hits newer than `cursor`
  (`w1.<newest_ms>.<expiry_ms>`, opaque to the agent). A poll with a cursor
  is a long poll: it re-reads the search until a new sighting arrives or
  `wait_seconds` (default 30, max 120, capped by `DEFAULT_WAIT_SECONDS` and
  the expiry) runs out, sending MCP progress notifications meanwhile, so
  `poll_after_seconds` is `0`. When `GET /search/refresh-config` reports
  auto-refresh disabled, nothing new can arrive: the poll returns at once with
  an `error` pointing at `vss_get_search refresh=true`, and
  `poll_after_seconds` is the configured interval. Expiry
  (`duration_minutes`) is applied on the next poll, which unwatches and
  returns `expired: true`.
- **Live cameras.** The stream tools wrap `/streams` (`GET`, `POST`,
  `POST /streams/batch`, `PATCH /{id}`, `DELETE /{id}` without purge) and are
  registered only with `imageSearchEnabled`. Every URL, name and error is
  credential-redacted. Live hits carry `source`, `stream_id`, `observed_at`
  (segment epoch from `media_path` plus the frame offset) and `raw_score`;
  their gateway-relative segment URL is prefixed with the datastore URL.
  `stream_ids` on search and watch is a post-filter on the ranked hits.
- **Hits locate their best frame.** A hit's `frame` is the search backend's
  `best_frame_info` cut down to what `GET /frames` takes (`video_id`,
  `timestamp`, `bucket_name`, `media_path` for live streams, `crop_bbox` for
  detected objects); `label` names the detected object. `vss_get_media_frame`
  passes those to `GET /frames?format=json` and returns the JPEG as MCP image
  content plus the frame metadata. If a live-stream hit arrives without
  `bucket_name`, the tool takes it from the camera's record, or uses
  `live-streams` when the camera was removed.
- **Indexing path is chosen for you.** When a frame-embedding index is
  deployed (dual or search-only mode; `imageSearchEnabled` in
  `/app/features`), the standalone frame-embedding endpoint
  (`POST /videos/search-embeddings/{id}`) is used — fast, and independent of
  summary. Otherwise (unified mode), summarizing populates the index instead,
  since the frame-embedding endpoint targets the wrong model there. Override
  with `VSS_INDEX_STRATEGY`. There is no batch tool.
- **`indexed` comes from the video row, and only when search is enabled.**
  `true` if `searchEmbeddings` or `textEmbeddings` is set, `false` if one is
  explicitly unset, `null` if neither is reported. The field (and
  `videos_indexed`/`videos_index_unknown` on `vss_get_deployment_info`) is
  absent entirely in a summary-only deployment, which has no search index.
  Pipeline Manager writes these flags when frame embeddings (single or batch)
  or summary-caption embeddings finish; videos embedded before that tracking
  existed stay `null`. Do not re-index just because the value is `null`.
- **Search hits carry a reachable `url`** under
  `http://<VSS_IP>:<APP_HOST_PORT>/datastore`, with `start_s`/`end_s`/`seek_s`
  in seconds. Search hits, captions and summaries are never truncated; only
  listing tools (videos, tags, searches, cameras) are trimmed to an
  8,000-byte budget (`truncated: true`).
- **Time filters are absolute.** `start` and `end` are ISO-8601 and both are
  required. The agent resolves "last 2 hours" using `server_time_utc` from
  `vss_get_deployment_info`.
- **Resources are dated snapshots; tools are live.** `vss://deployment`,
  `vss://videos` and `vss://tags` return the matching tool's JSON plus
  `as_of` (read time, UTC) and `refresh_with` (the tool that re-reads it).
  Clients usually attach a resource once, and the stateless server sends no
  change notifications, so after an upload or index call the tool rather than
  trusting attached context. `vss://deployment` omits `server_time_utc` so a
  frozen clock never skews a time range. `vss://search-patterns` is static.
- **No single-video search tool.** Search library-wide and filter hits by
  `video_id`.
- **Errors.** Backend failures return `isError` results with an actionable
  message. Unexpected internal errors are masked.

## Image search (claim-check)

```bash
HOST=http://<VSS_IP>:12345
curl -s -X POST "$HOST/manager/search/images" -F image=@query.jpg
# -> {"imageId":"<uuid>.jpg","imageUrl":"http://<host>/datastore/<bucket>/search-images/<uuid>.jpg",
#     "imagePath":"/datastore/<bucket>/search-images/<uuid>.jpg", ...}
```

Pass `imageUrl` (or `imagePath`/`imageId`) as `image` to `vss_search_video`.
`is_image_reference()` in `clients/vss.py` recognises it and sends
`{"imageUrl": ...}`. Pipeline Manager ignores the host and only accepts paths in
its own bucket under `search-images/`. The host in `imageUrl` comes from
`PM_PUBLIC_BASE_URL` (set by `setup.sh`) or the request's forwarded host.

| Status | Cause |
|---|---|
| 400 | Image search not enabled in this mode, both `query` and `image` given, or a URL outside the upload bucket |
| 404 | The uploaded image was deleted or never existed |
| 413 / 415 | Upload over 2 MB, or not jpg/jpeg/png/webp |
| 422 | Stored bytes do not match the file extension |

## Common failure modes

| Symptom | Cause and fix |
|---|---|
| Container restarts in a loop, log says to set `HOST_IP` | `HOST_IP` unset. Export it or pass it on the `up` command |
| Startup fails reaching `/manager/app/features` | VSS is not up, or `VSS_IP`/`APP_HOST_PORT` are wrong. Check `curl http://<VSS_IP>:12345/manager/health` |
| Inspector shows a corporate proxy error page | Proxy injected by Docker. Node matches `no_proxy` by exact host, not by CIDR; `mcp/compose.yaml` already adds `mcp-server` and `HOST_IP` |
| Inspector returns 403 on connect | Browser origin not in `ALLOWED_ORIGINS`. Browse at `http://localhost:6274` or `http://127.0.0.1:6274` on `INSPECTOR_PORT` |
| "Add Server" fails with `crypto.randomUUID is not a function` | Inspector was opened from `http://<HOST_IP>:6274` (plain HTTP, non-localhost host) -- not a secure context, so the browser hides `crypto.randomUUID()`. Browse to `http://localhost:6274` instead; from a different machine, `ssh -L 6274:localhost:6274 <user>@<host-ip>` and browse to `localhost` there. The target MCP server is not at fault |
| Search tools missing | Search feature off, or the server started before the mode changed. Restart it |
| `--remove-orphans` took VSS down | Never use it with the MCP-only compose file set. `setup.sh` sets `COMPOSE_IGNORE_ORPHANS=true` instead |

## Inspector settings (`mcp/compose.yaml`)

Standalone and name/port-isolated from the VSS stack's own `vss-mcp-server`
container, so it runs alongside a live deployment without stopping it.
`mcp-inspector` alone is enough to debug that deployment's MCP server at
`http://<HOST_IP>:<APP_HOST_PORT>/mcp`; the optional `mcp-server` service here
is only for exercising an uncommitted code change.

| Variable | Default |
|---|---|
| `MCP_HOST_PORT` | `8001` (optional dev build only; the VSS stack's own server is not published on the host) |
| `MCP_LOG_LEVEL` | `DEBUG` |
| `INSPECTOR_PORT` | `6274` |
| `INSPECTOR_BIND_ADDRESS` | `0.0.0.0` (set `127.0.0.1` for loopback only) |
| `INSPECTOR_TAG` | `2.10.0` |
| `DANGEROUSLY_OMIT_AUTH` | `false` (set `true` to skip the logged `Auth token`, trusted networks only) |
| `MCP_INSPECTOR_API_TOKEN` | generated per launch |
