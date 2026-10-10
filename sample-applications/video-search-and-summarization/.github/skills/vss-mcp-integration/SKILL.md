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

| Tool | Needs |
|---|---|
| `vss_get_deployment_info`, `vss_list_videos`, `vss_list_tags`, `vss_resolve_video` | — |
| `vss_index_video`, `vss_search_video`, `vss_get_search`, `vss_list_searches`, `vss_refetch_search`, `vss_watch_search` | search |
| `vss_summarize_video`, `vss_get_video_timeline` | summary |

Resources: `vss://deployment`, `vss://videos`, `vss://tags`, plus
`vss://search-patterns` with search. The live resources are dated snapshots
(`as_of`, `refresh_with`) of the matching tool, without `server_time_utc`. Prompts:
`search_videos` and `upload_and_index_videos` (search), `summarize_video`
(summary); the upload steps give the exact `curl` to `POST /manager/videos`
before `vss_index_video`/`vss_summarize_video`. Video upload is deliberately **not** a tool: callers POST to
`upload_url` from `vss_get_deployment_info` (`/manager/videos`, field `video`).

## Run and connect

Bring VSS up first. There are three ways to run the server:

| Way | Command | MCP URL | Inspector |
|---|---|---|---|
| Deployment profile | `source setup.sh --mcp` (stop: `--stop-mcp`) | `http://<HOST_IP>:8000/mcp` | no |
| Dev stack, from `mcp/` | `HOST_IP=<ip> docker compose up --build -d` | `http://<HOST_IP>:8000/mcp` | `http://<HOST_IP>:6274` |
| Local Poetry, from `mcp/` | `poetry install && HOST_IP=<ip> poetry run mcp-app` | `http://<HOST_IP>:8000/mcp` | no |

- `setup.sh --mcp` uses `docker/compose.mcp.yaml` and runs **only** the MCP
  server; it never starts MCP Inspector. Do not add Inspector to it.
- `mcp/compose.yaml` is the dev-only stack: it builds the same image
  (`${REGISTRY}vss-mcp-server:${TAG}`) and runs the same `vss-mcp-server`
  container on port 8000 as `setup.sh --mcp`, plus `vss-mcp-inspector`, with
  `LOG_LEVEL=DEBUG`. Run one or the other: `source setup.sh --stop-mcp` before
  starting it. A dev build replaces the image setup.sh runs. In Inspector, choose **Streamable HTTP** and connect to
  `http://mcp-server:8000/mcp`. Stop with `docker compose down` (no `HOST_IP`
  needed). Inspector auth is off (`DANGEROUSLY_OMIT_AUTH=true`), so warn the
  user it is for trusted networks only.
- Clients connect with the **Streamable HTTP** transport; there is no stdio mode.

Scripted check through the dev stack's Inspector CLI:

```bash
cd mcp
docker compose exec mcp-inspector mcp-inspector --cli \
  http://mcp-server:8000/mcp --transport http --method tools/list
```

## Real config keys

From `mcp/src/core/config.py`. The server needs `VSS_IP` or, as its fallback,
`HOST_IP`. `setup.sh --mcp` detects `HOST_IP` and asks for `VSS_IP` (default
`HOST_IP`) only when it is not already set; `docker/compose.mcp.yaml` requires
`VSS_IP` when run by hand.

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

`vss_search_video` takes exactly one of `query` or `image`. Prefer a
**reference** to an image uploaded with Pipeline Manager
`POST /manager/search/images` (multipart field `image`, jpg/jpeg/png/webp,
≤ 2 MB): pass the returned `imageUrl`, `imagePath` or `imageId`. The tool
forwards it as `imageUrl` on `POST /search`, and Pipeline Manager reads the
bytes from its own MinIO bucket, so no image data passes through MCP. Arbitrary
external URLs are rejected with 400 by design (SSRF protection). A `data:` URL or
a local file path readable by the server also works. Image search needs a
frame-embedding mode (`--search` or `--dual`); otherwise the search call returns
400. Delete uploads with `DELETE /manager/search/images/{imageId}`.

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
2. Check the server log: `docker logs vss-mcp-server` (setup.sh) or
   `cd mcp && docker compose logs mcp-server` (dev stack). The startup line
   `Deployment features: [...]` shows what was registered.
3. The feature set is read once. Restart the MCP server after changing the VSS
   mode.
4. For a new tool, confirm it is registered in its module's `register()` and
   that the image was rebuilt (`--build`).
5. Use Inspector (dev stack) or the CLI above to list tools directly, which
   rules out client-side caching.

See [references/mcp-server.md](references/mcp-server.md) for the request flow,
behaviours worth knowing and common failure modes.
