<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Video Search and Summarization MCP Server

The **MCP (Model Context Protocol) server** for the
[Video Search and Summarization (VSS)](https://github.com/open-edge-platform/edge-ai-libraries)
sample application. It exposes VSS as a set of tools for agents, and IDE extensions.

## Tools

The **Needs** column is what a deployment must have for the tool to exist at
all: at startup the server reads `GET /app/features` and registers only the
tools that deployment can serve.

Hits from a live camera carry `source: "live"`, `stream_id`, `observed_at`
(wall-clock UTC of the matched frame) and `raw_score` (the absolute
similarity; `score` is normalized so the top hit is 1). `vss_remove_stream`
is the only tool that deletes anything, and is annotated destructive.

| Tool | Needs | Purpose |
|---|---|---|
| `vss_get_deployment_info` | — | Which features are on, how much of the library is indexed (search only), and where to upload a video |
| `vss_list_videos` | — | Library listing, each with an `indexed` flag (search only) |
| `vss_list_tags` | — | The tag vocabulary a filter has to be drawn from |
| `vss_resolve_video` | — | Turn "the warehouse clip" into a video id |
| `vss_index_video` | search | Make a video searchable (call once per video) |
| `vss_search_video` | search | Find moments across indexed videos and live cameras, by text query or by image, optionally kept to some cameras (`stream_ids`) or to strong matches (`min_peak_score`, 0-1); the search is saved in VSS's search history |
| `vss_get_search` | search | A saved search and its latest results, by `query_id`; `refresh=true` (or `start`/`end`/`min_peak_score`) re-runs it first |
| `vss_list_searches` | search | Saved searches (VSS search history), newest first; `watched_only` for active watches |
| `vss_watch_search` | search | Track someone or something live: start a watched search (from a `query`, `image`, or a hit's `frame` via `from_hit`, over a rolling `window_minutes`), poll it with `cursor` (each poll waits up to `wait_seconds`, default 30, for a new sighting) for new sightings and `last_seen` per camera, and stop it (`watch=false`, or automatically after `duration_minutes`) |
| `vss_get_media_frame` | search | The image of a search hit's best-matching frame, from the hit's `frame` locator; crops to the detected object when the hit has a `crop_bbox`. Returns the image inline plus a shareable `url` |
| `vss_list_streams` | search | Registered RTSP cameras with state and ingest stats; filter by `state` or `tags` |
| `vss_get_stream` | search | One camera's state, stats and last error |
| `vss_add_stream` | search | Add one or more RTSP cameras (batch with `streams`); ingestion starts in the background |
| `vss_update_stream` | search | Pause/resume a camera or change its name, tags, frame interval or detection settings |
| `vss_remove_stream` | search | Stop and deregister cameras; their recorded footage and embeddings are kept (never purged) |
| `vss_summarize_video` | summary | Summarize a video and return only its final summary, in full (`final_summary=false` returns the timeline instead); sampling, Ingestion pipeline and audio are configurable, with the VSS UI defaults |
| `vss_get_video_summary_timeline` | summary | Full timeline (and final summary, if produced) of an already-summarized video |

**Uploading a video is not a tool.** Call `vss_get_deployment_info` for
`upload_url` (`http://<VSS_IP>:<APP_HOST_PORT>/manager/videos`); have the file
POSTed there — by the user or their own tooling, outside this server — as
`multipart/form-data` with field `video`, then pass the returned `videoId` to
`vss_index_video`.

## Quick start

**The MCP server runs with every VSS deployment.** It is a part of the VSS
deployment rather than a stack of its own — same Compose project, same
`vs_network`, same `.env` — and `setup.sh` starts it along with everything
else. At startup it probes `GET /app/features` and registers only the tools
that deployment can serve.

```bash
cd sample-applications/video-search-and-summarization
source setup.sh --search   # or --summary, --dual, --unified
```

| Service | URL |
|---|---|
| MCP Server (via nginx gateway) | `http://<HOST_IP>:<APP_HOST_PORT>/mcp` (default port `12345`) |

Point any MCP client that supports the **Streamable HTTP** transport at that
URL, or use MCP Inspector as described next.

## Debugging with MCP Inspector

`setup.sh` does not start MCP Inspector, but it can connect to the running
deployment's MCP server without stopping anything. From `mcp/`:

```bash
cd mcp
HOST_IP=<vss-host-ip> docker compose up -d mcp-inspector
```

Open Inspector at **`http://localhost:6274`** then choose **Streamable HTTP** and connect to
**`http://<HOST_IP>:<APP_HOST_PORT>/mcp`** (default `http://<HOST_IP>:12345/mcp`),
the running deployment's own MCP server.

If your browser runs on the host, use `http://localhost:6274` directly. If it runs elsewhere, tunnel instead of using the bare IP:

```bash
ssh -L 6274:localhost:6274 <user>@host-ip>
```

then open `http://localhost:6274` locally.

Inspector auth is on by default; find the session token with
`docker compose logs mcp-inspector`. Only set `DANGEROUSLY_OMIT_AUTH=true` on
a trusted, isolated network.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VSS_IP` | `HOST_IP` | Host of the VSS gateway, reachable by your agent; a bare IP or hostname |
| `HOST_IP` | auto-detected by `setup.sh` | This host's address; the fallback for `VSS_IP` and the host shown in the MCP URL |
| `APP_HOST_PORT` | `12345` | VSS gateway port |
| `MCP_HOST` / `MCP_PORT` / `MCP_PATH` | `0.0.0.0` / `8000` / `/mcp` | Listener (the VSS stack pins `8000` and `/mcp` to match the nginx route) |
| `REQUEST_TIMEOUT` | `60` | Per-HTTP-call timeout, seconds |
| `POLL_INTERVAL` | `5` | Delay between pipeline polls, seconds |
| `DEFAULT_WAIT_SECONDS` | `600` | Budget for tools that wait on a pipeline |
| `VSS_INDEX_STRATEGY` | `auto` | `auto`, `summary`, or `embeddings` |
| `LOG_LEVEL` | `INFO` | Python log level |

