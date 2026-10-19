---
name: vss-mcp-integration
description: Helps developers run, debug and extend the Video Search and Summarization sample app's MCP tool server (hand-declared FastMCP tools over Pipeline Manager). Use when the user wants to connect an AI agent to VSS, start the VSS MCP server, debug it with MCP Inspector, add an MCP tool to VSS, search by image through MCP, or debug why an MCP tool isn't showing up.
---

# VSS MCP Integration

Use this for `sample-applications/video-search-and-summarization/mcp`: the MCP
server that exposes VSS search and summary to agents as **hand-declared tools**
over the Pipeline Manager API, served over Streamable HTTP. There is no
OpenAPI-driven proxy, `search.json` filter, `API_SPEC_URL` or `mcp/.env` any
more. If a user mentions them, they are on an older release.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It first tries to find an existing VSS checkout -
walking up from the current directory and inspecting the enclosing git repo - and
reuses it **without ever re-cloning**. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/video-search-and-summarization` from `main`. It prints the
resolved app root on stdout:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-mcp-integration. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-mcp-integration"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it.

## Ground truth files

Read these before changing behaviour: `mcp/src/main.py`, `mcp/src/server.py`,
`mcp/src/features.py`, `mcp/src/core/config.py`, `mcp/src/clients/vss.py`,
`mcp/src/tools/*.py`, `mcp/src/context.py`, `mcp/README.md`,
`docs/user-guide/mcp-server.md`, `docker/compose.mcp.yaml`,
`mcp/compose.yaml`, and `mcp/tests/*`.

## How the server works

`src.main:main` (Poetry script `mcp-app`) calls `get_settings()`, then
`build_mcp()`, which probes `GET /manager/app/features` once and registers only
the tools, resources and prompts that feature set can serve
(`features.py`, `tools/__init__.py`, `context.py`). If VSS is unreachable the
process exits instead of guessing, and the container restart policy retries.
In the VSS stack, `docker/compose.mcp.yaml` starts it only after
`pipeline-manager` is healthy and `nginx` has started.

| Tool | Needs |
|---|---|
| `vss_get_deployment_info`, `vss_list_videos`, `vss_list_tags`, `vss_resolve_video` | — |
| `vss_index_video`, `vss_search_video`, `vss_get_search`, `vss_list_searches`, `vss_watch_search`, `vss_get_media_frame` | search |
| `vss_list_streams`, `vss_get_stream`, `vss_add_stream`, `vss_update_stream`, `vss_remove_stream` | live (search + `imageSearchEnabled`) |
| `vss_summarize_video`, `vss_get_video_summary_timeline` | summary |

`vss_watch_search` is also the live tracker: start (`query`/`image`/`from_hit`,
`window_minutes`, `duration_minutes`), poll (`query_id` + `cursor`), stop
(`watch=false`, or auto-expiry on the first poll after `duration_minutes`).
`min_peak_score` (0-1) gates the watch at retrieval on every VSS refresh and is
saved on the search; `min_raw_score` only filters the sightings one call reports.
`vss_remove_stream` is the only destructive tool and never purges footage.

Resources: `vss://deployment`, `vss://videos`, `vss://tags`, plus
`vss://search-patterns` with search. Cameras are deliberately a tool only (`vss_list_streams`), not a resource, since their state changes constantly. The live resources are dated snapshots
(`as_of`, `refresh_with`) of the matching tool, without `server_time_utc`. Prompts:
`search_videos` (search), `monitor_camera` and `track_object` (live),
`summarize_video` (summary); `summarize_video` gives the exact `curl` to
`POST /manager/videos` before `vss_summarize_video`.
`vss_get_media_frame` returns the JPEG inline (MCP image content, visible to
vision-capable agents) plus a `url` to the same image at
`/manager/frames?...&format=image`. Video upload is deliberately **not** a tool: callers POST to
`upload_url` from `vss_get_deployment_info` (`/manager/videos`, field `video`).

## Run and connect

The MCP server **runs with every VSS deployment** (`source setup.sh <mode>`); it
probes `GET /manager/app/features` at startup and registers only the tools the
deployment can serve. There are three ways to run it:

| Way | Command | MCP URL | Inspector |
|---|---|---|---|
| VSS stack (default) | `source setup.sh --search` (any mode) | `http://<HOST_IP>:12345/mcp` (nginx gateway) | no |
| Inspector only, from `mcp/` | `HOST_IP=<ip> docker compose up -d mcp-inspector` | n/a (points at the VSS stack's URL above) | `http://localhost:6274` |
| Dev build + Inspector, from `mcp/` | `HOST_IP=<ip> docker compose up --build -d` | `http://<HOST_IP>:8001/mcp` | `http://localhost:6274` |
| Local Poetry, from `mcp/` | `poetry install && HOST_IP=<ip> poetry run mcp-app` | `http://<HOST_IP>:8000/mcp` | no |

- The VSS stack runs the MCP server via `docker/compose.mcp.yaml` (profile
  `mcp`) and never starts MCP Inspector. `source setup.sh --stop` brings the
  MCP server down with the rest of the stack.
- `mcp/compose.yaml` is standalone and never needs the VSS stack stopped: its
  `mcp-inspector` service alone (`up -d mcp-inspector`) is enough to debug the
  **running deployment's own** MCP server — just open Inspector and connect it
  to the VSS stack's URL (`http://<HOST_IP>:12345/mcp`). Only start this
  file's optional `mcp-server` service to exercise an uncommitted code change;
  it builds `${REGISTRY}vss-mcp-server:${TAG:-dev}` as a separate
  `vss-mcp-server-dev` container on its own host port (`${MCP_HOST_PORT:-8001}`),
  so it never collides with the deployment's `vss-mcp-server` container or its
  `:12345/mcp` route and both can run at once. In Inspector, choose
  **Streamable HTTP** and connect to `http://<HOST_IP>:12345/mcp` (the
  deployment) or `http://<HOST_IP>:8001/mcp` (a dev build). Stop with
  `docker compose stop mcp-inspector` (or `down` to also drop a dev build).
  Inspector auth is on by default (`DANGEROUSLY_OMIT_AUTH=false`); the
  token is printed in `docker compose logs mcp-inspector`. Warn the user that
  setting `DANGEROUSLY_OMIT_AUTH=true` is only for trusted, isolated networks.
- **Always browse to `http://localhost:6274`, never `http://<HOST_IP>:6274`.**
  Browsers only expose `crypto.randomUUID()` — which Inspector's UI calls to
  connect to any server — in a secure context (HTTPS, or `localhost`/
  `127.0.0.1`). Opening Inspector from the bare host IP over plain HTTP makes
  every "Add Server" attempt fail with `crypto.randomUUID is not a function`,
  even though the target MCP server is perfectly reachable. If the browser is
  on a different machine than the Docker host, tunnel instead of using the IP:
  `ssh -L 6274:localhost:6274 <user>@<host-ip>`, then browse to
  `http://localhost:6274` locally.
- Clients connect with the **Streamable HTTP** transport; there is no stdio mode.

Scripted check through the standalone Inspector's CLI, against the running
deployment:

```bash
cd mcp
docker compose exec mcp-inspector mcp-inspector --cli \
  http://<HOST_IP>:12345/mcp --transport http --method tools/list
```

## Real config keys

From `mcp/src/core/config.py`. The server needs `VSS_IP` or, as its fallback,
`HOST_IP`. The VSS stack sets both: `HOST_IP` is auto-detected by `setup.sh`
and `VSS_IP` defaults to it (override in `.env` only when the gateway runs
elsewhere); `docker/compose.mcp.yaml` requires `VSS_IP` when run by hand.

| Variable | Default | Purpose |
|---|---|---|
| `VSS_IP` | `HOST_IP` | VSS gateway host reachable by the agent; every VSS URL uses it |
| `HOST_IP` | auto-detected by `setup.sh` | This host; fallback for `VSS_IP`, host in the MCP URL |
| `APP_HOST_PORT` | `12345` | VSS gateway port |
| `MCP_HOST` / `MCP_PORT` / `MCP_PATH` | `0.0.0.0` / `8000` / `/mcp` | Listener |
| `MCP_STATELESS_HTTP` | `true` | Streamable HTTP statelessness |
| `REQUEST_TIMEOUT` / `POLL_INTERVAL` / `DEFAULT_WAIT_SECONDS` | `60` / `5` / `600` | Seconds |
| `VSS_INDEX_STRATEGY` | `auto` | `auto`, `summary`, or `embeddings` |
| `LOG_LEVEL` | `INFO` | Python log level |

All VSS calls go through the gateway: `http://<VSS_IP>:<APP_HOST_PORT>/manager`
and `.../datastore`. Settings come from the app-root `.env`; there is no MCP env
file.

## Search by image 

`vss_search_video` takes exactly one of `query` or `image`. `image` must be a
**reference** to an image already uploaded directly to VSS with
`POST /manager/search/images` (multipart field `image`, jpg/jpeg/png/webp,
≤ 2 MB): pass the returned `imageUrl`, `imagePath` or `imageId`. The tool
forwards it as `imageUrl` on `POST /search`, and Pipeline Manager reads the
bytes from its own MinIO bucket, so no image data ever passes through MCP --
the server reads no local files and accepts no inline/`data:` image bytes
from a caller; anything else is rejected with a message pointing at the
upload endpoint. Arbitrary external URLs are rejected with 400 by design
(SSRF protection). Image search needs a frame-embedding mode (`--search` or
`--dual`); otherwise the search call returns 400. Delete uploads with
`DELETE /manager/search/images/{imageId}`.

## Add a tool

1. Add an async function to the right module in `mcp/src/tools/`, taking `Deps`
   first and returning a projection (see `projections.py`), capped with
   `cap_payload`.
2. Register it in that module's `register()` with `@mcp.tool(annotations=...)`
   and a docstring written for a model. Gate it on `deps.features` if it needs
   search or summary.
3. Add a test in `mcp/tests/test_tools.py` against `FakeVss` (shared fixtures
   live in `mcp/tests/fakes.py`; the suite blocks real network access), then run
   `cd mcp && uv run pytest`. The named-tool tests in
   `tests/test_server.py` fail if a prompt or description names a tool that
   isn't registered.

## Debug a missing tool

1. Check the feature gate: `curl http://<VSS_IP>:12345/manager/app/features`.
   Search tools need `search: FEATURE_ON`, summary tools need
   `summary: FEATURE_ON`. `vss_get_deployment_info` reports the same.
2. Check the server log: `docker logs vss-mcp-server` (VSS stack) or
   `cd mcp && docker compose logs mcp-server` (a dev build, container
   `vss-mcp-server-dev`). The startup line `Deployment features: [...]` shows
   what was registered.
3. The feature set is read once. Restart the MCP server after changing the VSS
   mode (or re-deploy).
4. For a new tool, confirm it is registered in its module's `register()` and
   that the image was rebuilt (`--build`).
5. To trace what an agent actually called, read the server log: each call
   logs `tool <name> ok|failed in <ms>` under a `[call id]` that also tags its
   `VSS <METHOD> <path> -> <status>` lines; `LOG_LEVEL=DEBUG` adds the
   (credential-masked) arguments. See "Tracing agent calls" in `mcp/README.md`.
6. Use Inspector (`docker compose up -d mcp-inspector`, no dev build needed)
   or the CLI above to list tools directly, which rules out client-side
   caching.

See [references/mcp-server.md](references/mcp-server.md) for the request flow,
behaviours worth knowing and common failure modes.
