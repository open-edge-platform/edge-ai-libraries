# MCP Server for VSS

The VSS MCP server exposes [Video Search and Summarization (VSS)](./index.md) to
AI agents and IDE extensions using the
[Model Context Protocol (MCP)](https://modelcontextprotocol.io/). It is served
over **Streamable HTTP** and presents a set of tools over the VSS
Pipeline Manager API.
## Prerequisites

- The **VSS application must be running and reachable** before starting this server.
- Docker and Docker Compose installed ([Installation Guide](https://docs.docker.com/get-docker/)).
- Network access from the machine running this container to the VSS host.

## Quick Start

All commands below are run from the application root:

```bash
cd sample-applications/video-search-and-summarization
```

The MCP server is a **profile of the VSS deployment**, not a stack of its own, every tool it exposes is a call into Pipeline Manager.

1. **Build and start.**:

   ```bash
   source setup.sh --mcp
   ```

   No exports are needed. `setup.sh` detects `HOST_IP` itself, then asks for
   `VSS_IP` — the VSS gateway host the MCP server calls and puts in every URL
   it returns to agents:

   ```
   VSS_IP (VSS gateway host reachable by your agent) [<detected HOST_IP>]:
   ```

   Press Enter to use the detected address, or type the host your agent
   reaches VSS on. If `VSS_IP` is already exported or set in `.env`, it is
   used without asking. Without a terminal, `HOST_IP` is used.

2. **Connect an Agent.** Point any MCP client or agent that supports the
   **Streamable HTTP** transport at:

   | Service        | URL                              | Description                        |
   |----------------|----------------------------------|------------------------------------|
   | MCP Server     | `http://<HOST_IP>:8000/mcp`      | Streamable HTTP MCP endpoint       |

3. **Stop.** Stop only the MCP server and leave VSS running:

   ```bash
   source setup.sh --stop-mcp
   ```

   `source setup.sh --stop` brings the MCP server down with the rest of VSS.


## Runtime Configuration

| Variable                    | Required          | Default            | Description                                           |
|-----------------------------|-------------------|--------------------|-------------------------------------------------------|
| `VSS_IP`                    | **Yes**           | asked by `setup.sh --mcp` (default `HOST_IP`) | Host of the VSS gateway, reachable by your agent; every VSS URL is built from it. Not asked for when already set |
| `HOST_IP`                   | No                | auto-detected by `setup.sh` | This host's address; fallback for `VSS_IP` and the host in the MCP URL |
| `APP_HOST_PORT`             | No                | `12345`            | VSS gateway port                                      |
| `MCP_HOST`                  | No                | `0.0.0.0`          | Bind address                                          |
| `MCP_PORT`                  | No                | `8000`             | Listening port                                        |
| `MCP_PATH`                  | No                | `/mcp`             | Streamable HTTP endpoint path                         |            |

## What MCP Clients See

### Available tools

The **Needs** column is the VSS feature a tool requires. `vss_get_deployment_info` reports
the feature set behind the decision.

| Tool | Needs | Purpose |
|---|---|---|
| `vss_get_deployment_info` | — | Which features are on, and how much of the library is indexed (search only) |
| `vss_list_videos` | — | Library listing, each entry with an `indexed` flag (search only) |
| `vss_list_tags` | — | The tags videos are labelled with |
| `vss_resolve_video` | — | Turn "the warehouse clip" into a video id |
| `vss_index_video` | search | Make a video searchable (call once per video) |
| `vss_search_video` | search | Find moments across indexed videos; the search is saved in VSS's search history |
| `vss_get_search` | search | A saved search and its latest results |
| `vss_list_searches` | search | Saved searches, newest first |
| `vss_refetch_search` | search | Re-run a saved search |
| `vss_watch_search` | search | Watch a saved search so VSS re-runs it when new videos are indexed |
| `vss_summarize_video` | summary | Summarize a video: a timeline plus, by default, a final summary |
| `vss_get_video_timeline` | summary | Timeline (and final summary, if produced) of an already-summarized video |


## Video Upload

`POST /videos` is intentionally **not** exposed. Video upload is a long-running multipart operation better handled directly via the VSS REST API. Use the MCP server for discovery, search and status workflows only.
