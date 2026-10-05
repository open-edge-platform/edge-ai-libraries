<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Video Search and Summarization MCP Server

The **MCP (Model Context Protocol) server** for the
[Video Search and Summarization (VSS)](https://github.com/open-edge-platform/edge-ai-libraries)
sample application. It exposes VSS as a set of tools for agents, and IDE extensions.

## Project structure

```
mcp/                             ← cd here for tests and source work
├── pyproject.toml
├── Dockerfile
├── compose.yaml                 # dev stack: server + MCP Inspector (not used by setup.sh)
│
├── src/
│   ├── main.py                  # Process entrypoint
│   ├── server.py                # FastMCP factory, tool registration
│   ├── features.py              # Startup probe: what this deployment can do
│   ├── context.py               # Resources and prompts
│   ├── projections.py           # Wire payloads → agent-sized results
│   ├── core/config.py           # Settings and environment parsing
│   ├── clients/vss.py           # Typed Pipeline Manager client
│   └── tools/
│       ├── _deps.py             # Shared dependencies and domain helpers
│       ├── discovery.py         # deployment info, list, tags, resolve
│       ├── ingest.py            # index one, index many
│       ├── summary.py           # summarize, timeline
│       └── search.py            # search, search within a video
│
└── tests/                       # unit tests, no deployment required
```


## Tools

The **Needs** column is what a deployment must have for the tool to exist at
all: at startup the server reads `GET /app/features` and registers only the
tools that deployment can serve.

| Tool | Needs | Purpose |
|---|---|---|
| `vss_get_deployment_info` | — | Which features are on, how much of the library is indexed (search only), and where to upload a video |
| `vss_list_videos` | — | Library listing, each with an `indexed` flag (search only) |
| `vss_list_tags` | — | The tag vocabulary a filter has to be drawn from |
| `vss_resolve_video` | — | Turn "the warehouse clip" into a video id |
| `vss_index_video` | search | Make a video searchable (call once per video) |
| `vss_search_video` | search | Find moments across indexed videos, by text query or by image; the search is saved in VSS's search history |
| `vss_get_search` | search | A saved search and its latest results, by `query_id` |
| `vss_list_searches` | search | Saved searches (VSS search history), newest first |
| `vss_refetch_search` | search | Re-run a saved search, optionally over a new time range |
| `vss_watch_search` | search | Watch a saved search so VSS re-runs it when new videos are indexed |
| `vss_summarize_video` | summary | Summarize a video: a timeline plus, by default, a final summary; sampling, EVAM pipeline and audio are configurable, with the VSS UI defaults |
| `vss_get_video_timeline` | summary | Timeline (and final summary, if produced) of an already-summarized video |

**Uploading a video is not a tool.** This server has no way to accept file
bytes over MCP that is both safe and reliable across deployments: reading a
path only works when the caller's file already lives on this server's own
filesystem, and a general-purpose HTTP tool would turn this server into an
open proxy onto its network for one narrow feature. Call
`vss_get_deployment_info` for `upload_url`
(`http://<VSS_IP>:<APP_HOST_PORT>/manager/videos`); have the file POSTed there — by the user or their own
tooling, outside this server — as `multipart/form-data` with field `video`,
then pass the returned `videoId` to `vss_index_video`.


## Quick start

**The MCP server sits on top of VSS — bring VSS up first.** Every tool it
exposes is a call into Pipeline Manager, so on its own it has nothing to serve.

It is a **profile of the VSS deployment** rather than a stack of its own: same
Compose project, same `vs_network`, same `.env`. Its compose file lives in
[`../docker`](../docker) with the rest of the stack, and `setup.sh` starts it:

```bash
cd sample-applications/video-search-and-summarization
source setup.sh --mcp
```

`setup.sh --mcp` needs no exports:

- **`HOST_IP`** is detected from `ip route get 1`, as for a normal deploy.
  Export it only to override the detected address.
- **`VSS_IP`** — the VSS gateway host the server calls and puts in every URL it
  returns — is asked for at the prompt, defaulting to `HOST_IP` (press Enter to
  accept). If `VSS_IP` is already exported, or set in `.env`, it is used as-is
  and nothing is asked. Without a terminal (CI, scripts) it falls back to
  `HOST_IP` with a notice. It must be a bare IP or hostname reachable by your
  agent, never `localhost`.

`source setup.sh --stop-mcp` (or `make stop-mcp`) stops only the MCP server
and leaves VSS running; `--stop` brings it down with everything else.

To run it by hand, from the repository root:

```bash
export VSS_IP=$(ip route get 1 | awk '{print $7}')
COMPOSE_IGNORE_ORPHANS=true docker compose --env-file .env \
  -f docker/compose.base.yaml -f docker/compose.mcp.yaml \
  --profile mcp up --build -d mcp-server
```

Both leading pieces are load-bearing:

- **`--env-file .env`** — Compose resolves the default `.env` against the
  *project directory*, which is the directory of the first `-f` file (`docker/`),
  not against your shell's cwd. Without the flag settings such as
  `APP_HOST_PORT` and `VSS_IP` in the root `.env` are ignored.
- **`VSS_IP`** — the only required setting when running Compose by hand
  (`setup.sh` fills it in for you). Every URL the server calls or hands to
  agents is built from it.
- **`COMPOSE_IGNORE_ORPHANS=true`** — passing a subset of the project's compose
  files makes every other VSS container look like an orphan. Don't "fix" that
  warning with `--remove-orphans`; it would take the rest of the deployment down.

Behind a corporate proxy set `http_proxy`, `https_proxy` and `no_proxy`;
`HOST_IP` and `VSS_IP` are appended to `no_proxy` inside the container so the
server always reaches the gateway directly.

| Service | URL |
|---|---|
| MCP Server | `http://<HOST_IP>:8000/mcp` |

To try the tools interactively, point any MCP client that supports the
**Streamable HTTP** transport at that URL, or use MCP Inspector as described
next.


## Debugging with MCP Inspector

`setup.sh` does not start MCP Inspector. To debug the server from this folder,
with VSS running:

```bash
(cd .. && source setup.sh --stop-mcp)   # if the setup.sh server is running
HOST_IP=<vss-host-ip> docker compose up --build -d
```

This builds and runs the same image (`${REGISTRY}vss-mcp-server:${TAG}`,
default `vss-mcp-server:latest`) and the same `vss-mcp-server` container on
port 8000 as `setup.sh --mcp`, plus `vss-mcp-inspector`, with
`LOG_LEVEL=DEBUG`. Run one or the other, not both; a dev build also replaces
the image `setup.sh --mcp` runs.

Open **`http://<HOST_IP>:6274`**, choose **Streamable HTTP**, and connect to
**`http://mcp-server:8000/mcp`**. Stop it with `docker compose down`.

> **Warning:** Inspector auth is disabled in this dev stack. Use it only on a
> trusted network.


## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VSS_IP` | asked by `setup.sh --mcp`, defaulting to `HOST_IP` | Host of the VSS gateway, reachable by your agent; a bare IP or hostname. Not asked for when already set |
| `HOST_IP` | auto-detected by `setup.sh` | This host's address; the fallback for `VSS_IP` and the host shown in the MCP URL |
| `APP_HOST_PORT` | `12345` | VSS gateway port |
| `MCP_HOST` / `MCP_PORT` / `MCP_PATH` | `0.0.0.0` / `8000` / `/mcp` | Listener |
| `REQUEST_TIMEOUT` | `60` | Per-HTTP-call timeout, seconds |
| `POLL_INTERVAL` | `5` | Delay between pipeline polls, seconds |
| `DEFAULT_WAIT_SECONDS` | `600` | Budget for tools that wait on a pipeline |
| `VSS_INDEX_STRATEGY` | `auto` | `auto`, `summary`, or `embeddings` |
| `LOG_LEVEL` | `INFO` | Python log level |

Every VSS URL is derived from those three: Pipeline Manager at
`http://<VSS_IP>:<APP_HOST_PORT>/manager` (also the upload and frame links
handed to agents) and the datastore at `.../datastore`. The server always
goes through the gateway rather than the internal `pipeline-manager:3000`
address, so the links it returns are the ones it has itself reached.
Configuration comes from the application's root `.env`; there is no separate
MCP env file.


## Adding a tool

Tools are code now, so adding one is a small edit rather than a config change —
the trade for no longer being able to expose an endpoint by listing it.

1. Add an async function to the relevant module in `src/tools/`, taking `Deps`
   as its first argument, and returning a projected dict.
2. Register it inside that module's `register()` with an `@mcp.tool` wrapper
   whose docstring is written for a model to read.
3. Add a test in `tests/test_tools.py` against `FakeVss` (from `tests/fakes.py`).

Two rules for anything new: return a projection rather than the upstream
payload, and keep results inside the byte budget with `cap_payload`.


## Tests

From `mcp/`:

```bash
uv run pytest                                   # whole suite
uv run pytest tests/test_tools.py -k search     # a subset
```

`uv run` creates `.venv` from `pyproject.toml` and `uv.lock`, including the `dev` dependency group. Poetry reads the same `pyproject.toml` (`poetry install --with dev && poetry run pytest`).

