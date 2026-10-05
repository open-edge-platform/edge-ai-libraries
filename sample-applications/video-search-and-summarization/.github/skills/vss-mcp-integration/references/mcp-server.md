<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS MCP server reference

Sources: `mcp/src/**`, `mcp/compose.yaml`, `docker/compose.mcp.yaml`,
`pipeline-manager/src/search/**`.

## Request flow

```text
agent --Streamable HTTP--> MCP server (:8000/mcp)
      --HTTP--> nginx gateway http://<VSS_IP>:12345/manager/... --> Pipeline Manager
```

The server calls only the gateway, never `pipeline-manager:3000`, so every URL
it hands to an agent is one it has reached itself.

## Behaviours worth knowing

- **Surface follows the deployment.** `GET /app/features` is read once at
  startup. Tools, resources and prompts for a disabled feature are never
  registered. There is no way to force the surface by hand.
- **Summaries use the VSS defaults.** `vss_summarize_video` sends
  `produceFinalSummary: true` and polls until `videoSummaryStatus` is
  `"complete"`, like the UI. Sampling (8 s chunks, 8 frames, the deployment's
  overlap), EVAM pipeline (the deployment's) and audio (on, with
  `meta.defaultAudioModel` when there is one) also match the UI, and each can
  be overridden; invalid values are rejected before `POST /summary`. With
  `final_summary=false`, `videoSummaryStatus` ends at `"na"`, so polling keys
  off chunking completion plus a drained `frameSummaryStatus`. Summary-based
  indexing (`vss_index_video`) stays chunk-only without audio. If the wait
  budget runs out, the tool returns a `state_id` for `vss_get_video_timeline`.
- **Searches are persisted.** `vss_search_video` creates a query with
  `POST /search`, as the UI does, then polls `GET /search/{queryId}` until
  `queryStatus` leaves `running` (default budget 60 s, or `wait_seconds`). It
  returns `query_id` and `status`; `status: "running"` means fetch the hits
  later with `vss_get_search`. `vss_list_searches`, `vss_refetch_search` and
  `vss_watch_search` wrap `GET /search`, `POST /search/{id}/refetch` and
  `PATCH /search/{id}/watch`. A failed query (`queryStatus: "error"`) is
  returned as a tool error.
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
  Do not re-index just because the value is `null`.
- **Search hits carry a reachable `url`** under
  `http://<VSS_IP>:<APP_HOST_PORT>/datastore`, with `start_s`/`end_s`/`seek_s`
  in seconds. Output is multiline JSON inside an 8,000-byte budget; only whole
  hits are dropped (`truncated: true`), and URLs are never shortened.
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
| Inspector returns 403 on connect | Browser origin not in `ALLOWED_ORIGINS`. Browse at `http://<HOST_IP>:6274`, `localhost` or `127.0.0.1` on `INSPECTOR_PORT` |
| Search tools missing | Search feature off, or the server started before the mode changed. Restart it |
| `--remove-orphans` took VSS down | Never use it with the MCP-only compose file set. `setup.sh` sets `COMPOSE_IGNORE_ORPHANS=true` instead |

## Dev stack settings (`mcp/compose.yaml`)

| Variable | Default |
|---|---|
| `MCP_HOST_PORT` | `8000` |
| `MCP_LOG_LEVEL` | `DEBUG` |
| `INSPECTOR_PORT` | `6274` |
| `INSPECTOR_BIND_ADDRESS` | `0.0.0.0` (set `127.0.0.1` for loopback only) |
| `INSPECTOR_TAG` | `2.8.0` |
| `DANGEROUSLY_OMIT_AUTH` | `true` (set `false` to require the logged `Auth token`) |
| `MCP_INSPECTOR_API_TOKEN` | generated per launch |
