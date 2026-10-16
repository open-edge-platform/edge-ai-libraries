# MCP Server for VSS

The VSS MCP server exposes [Video Search and Summarization (VSS)](./index.md) to
AI agents and IDE extensions using the
[Model Context Protocol (MCP)](https://modelcontextprotocol.io/). It is served
over **Streamable HTTP** and presents a set of tools over the VSS
Pipeline Manager API.

For a task-oriented walkthrough, from connecting an agent to running real use
cases, see [Agentic Video Analytics with VSS](./agentic-video-analytics.md).
## Prerequisites

- Docker and Docker Compose installed ([Installation Guide](https://docs.docker.com/get-docker/)).
- A running VSS deployment (the MCP server starts with the stack and probes
  it at startup).
- Network access from the machine running this container to the VSS host.

## Quick Start

All commands below are run from the application root:

```bash
cd sample-applications/video-search-and-summarization
```

The MCP server **runs with every VSS deployment**: `source setup.sh <mode>`
(starts it) and `source setup.sh --stop` (stops it) manage it along with the
rest of the stack. It reads the enabled VSS features from Pipeline Manager at
startup, so no MCP-specific configuration is needed per mode.

1. **Start VSS** (any mode). The MCP server comes up with the stack and the
   final output shows its URL:

   ```bash
   source setup.sh --search   # or --summary, --dual, --unified
   ```

   `HOST_IP` is auto-detected. `VSS_IP` — the VSS gateway host the MCP server
   calls and puts in every URL it returns to agents — defaults to `HOST_IP`;
   set it in `.env` or your shell only when the VSS gateway runs on another
   machine.

2. **Connect an Agent.** Point any MCP client or agent that supports the
   **Streamable HTTP** transport at:

   | Service        | URL                              | Description                        |
   |----------------|----------------------------------|------------------------------------|
   | MCP Server     | `http://<HOST_IP>:12345/mcp`     | Streamable HTTP MCP endpoint, proxied by the nginx gateway |

3. **Stop.** Stop the MCP server together with the rest of VSS:

   ```bash
   source setup.sh --stop
   ```

## Runtime Configuration

| Variable                    | Required          | Default            | Description                                           |
|-----------------------------|-------------------|--------------------|-------------------------------------------------------|
| `VSS_IP`                    | No                | `HOST_IP`          | Host of the VSS gateway, reachable by your agent; every VSS URL is built from it. Not asked for when already set |
| `HOST_IP`                   | No                | auto-detected by `setup.sh` | This host's address; fallback for `VSS_IP` and the host in the MCP URL |
| `APP_HOST_PORT`             | No                | `12345`            | VSS gateway port                                      |
| `MCP_HOST`                  | No                | `0.0.0.0`          | Bind address                                          |
| `MCP_PORT`                  | No                | `8000`             | Listening port (pinned in the VSS stack; not published on the host) |
| `MCP_PATH`                  | No                | `/mcp`             | Streamable HTTP endpoint path (pinned in the VSS stack to match nginx) |

## What MCP Clients See

### Available tools

The **Needs** column is the VSS feature a tool requires. `vss_get_deployment_info` reports
the feature set behind the decision. **live** means search with a frame-embedding index
(`--search` or `--dual`); unified mode ingests no live cameras.

| Tool | Needs | Purpose |
|---|---|---|
| `vss_get_deployment_info` | — | Which features are on, and how much of the library is indexed (search only) |
| `vss_list_videos` | — | Library listing, each entry with an `indexed` flag (search only) |
| `vss_list_tags` | — | The tags videos and live cameras are labelled with |
| `vss_resolve_video` | — | Turn "the warehouse clip" into a video id |
| `vss_index_video` | search | Make a video searchable (call once per video) |
| `vss_search_video` | search | Find moments across indexed videos and live cameras; the search is saved in VSS's search history |
| `vss_get_search` | search | A saved search and its latest results; `refresh=true` re-runs it first |
| `vss_list_searches` | search | Saved searches, newest first |
| `vss_watch_search` | search | Track a person or object live: start a watched search, poll it for new sightings, stop it (or let it expire after `duration_minutes`) |
| `vss_get_media_frame` | search | The image of a search hit's best-matching frame (or its detected object), from the hit's `frame` locator |
| `vss_list_streams` | live | Registered RTSP cameras, with state and ingest stats |
| `vss_get_stream` | live | One camera's state, stats and last error |
| `vss_add_stream` | live | Add one or more RTSP cameras |
| `vss_update_stream` | live | Pause, resume or retune a camera |
| `vss_remove_stream` | live | Stop and deregister cameras; recorded footage and embeddings are kept |
| `vss_summarize_video` | summary | Summarize a video and return only its final summary, in full (`final_summary=false` returns the timeline instead) |
| `vss_get_video_summary_timeline` | summary | Full timeline (and final summary, if produced) of an already-summarized video |

## Video Upload

`POST /videos` is intentionally **not** exposed. Video upload is a long-running multipart operation better handled directly via the VSS REST API. Use the MCP server for discovery, search and status workflows only.
