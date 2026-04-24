# Video Search and Summarization — MCP Server

This directory contains the **MCP (Model Context Protocol) server** for the
[Video Search and Summarization (VSS)](https://github.com/open-edge-platform/edge-ai-libraries)
sample application.  It proxies a selected subset of VSS REST endpoints to MCP
clients (agents, IDE extensions, MCP Inspector, …) as **tools** and
**resources**, using the third-party [`fastmcp`](https://gofastmcp.com) library
to translate the live VSS OpenAPI spec into an MCP surface at startup.

The server is controlled by a **filter file** — a small JSON document that
lists exactly which VSS endpoints to expose and whether each appears as a tool
or a resource.  Three bundled filter files cover the three VSS deployment modes:

| VSS deployment mode | Filter file    |
|---------------------|---------------|
| Search only         | `search.json` |
| Summary only        | `summary.json`|
| Search + Summary    | `all.json`    |

`all.json` is the default when `FILTER_FILE_PATH` is not set.

---

## Prerequisites

The **VSS application must be running and reachable** before starting this
server.  You need:

1. the VSS REST service up (e.g. `http://<VSS_IP>:12345/manager`)
2. network access from the machine running this container to the VSS host
3. the VSS OpenAPI spec URL
   (e.g. `http://<VSS_IP>:12345/manager/swagger/json`)

---

## Quick start

Build the image from this `mcp/` directory:

```bash
docker build -t vss-mcp .
```

Run against a VSS backend (all-mode example):

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)/all.json:/app/all.json:ro" \
  -e API_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
  -e API_BASE_URL=http://<VSS_IP>:12345/manager \
  -e FILTER_FILE_PATH=/app/all.json \
  vss-mcp
```

The MCP server is then reachable at:

```
http://127.0.0.1:8000/mcp
```

---

## Selecting the right filter

Mount the filter file that matches the VSS mode you started:

```bash
# Search-only VSS backend
docker run --rm -p 8000:8000 \
  -v "$(pwd)/search.json:/app/search.json:ro" \
  -e API_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
  -e API_BASE_URL=http://<VSS_IP>:12345/manager \
  -e FILTER_FILE_PATH=/app/search.json \
  vss-mcp
```

```bash
# Summary-only VSS backend
docker run --rm -p 8000:8000 \
  -v "$(pwd)/summary.json:/app/summary.json:ro" \
  -e API_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
  -e API_BASE_URL=http://<VSS_IP>:12345/manager \
  -e FILTER_FILE_PATH=/app/summary.json \
  vss-mcp
```

## Runtime configuration

| Variable                  | Required            | Default          | Description                                          |
|---------------------------|---------------------|------------------|------------------------------------------------------|
| `API_SPEC_URL`            | **Yes**             | —                | URL to the VSS OpenAPI/Swagger JSON document         |
| `API_BASE_URL`            | Yes (recommended)   | from spec        | Base URL of the running VSS REST service             |
| `FILTER_FILE_PATH`        | No                  | bundled `all.json`| Path to the mounted filter file inside the container |
| `APP_PROXY_REQUEST_TIMEOUT` | No                | `60`             | Outbound request timeout in seconds                  |
| `LOG_LEVEL`               | No                  | `INFO`           | Python log level (`DEBUG`, `INFO`, `WARNING`, …)     |
| `MCP_HOST`                | No                  | `127.0.0.1`      | Bind address (use `0.0.0.0` in Docker)               |
| `MCP_PORT`                | No                  | `8000`           | Listening port                                       |
| `MCP_PATH`                | No                  | `/mcp`           | Streamable HTTP endpoint path                        |
| `MCP_STATELESS_HTTP`      | No                  | `true`           | Stateless streamable HTTP mode                       |

`API_BASE_URL` is resolved from the `servers` list in the OpenAPI spec when
not set explicitly.  Setting it explicitly is recommended to avoid surprises
when the spec contains a relative or environment-specific URL.

---

## What MCP clients see

At startup the server reads the VSS OpenAPI spec and the filter file, then
registers exactly the operations listed in the filter.

**Tools** (state-changing or parameterised operations) — examples from
`search.json`:

| Tool name                          | VSS endpoint                          |
|------------------------------------|---------------------------------------|
| `vss_run_search_query`             | `POST /search/query`                  |
| `vss_get_all_videos`               | `GET /videos`                         |
| `vss_get_video`                    | `GET /videos/{videoId}`               |
| `vss_create_video_search_embeddings` | `POST /videos/search-embeddings/{videoId}` |
| `vss_get_tags`                     | `GET /tags`                           |
| `vss_delete_tag`                   | `DELETE /tags/{tagId}`                |

Tool names are built from `"tool_prefix"` + `"tool_name"` in the filter file.

**Resources** (read-only, no body) are auto-named from the VSS `operationId`
field.  For example, `GET /app/features` with operationId
`AppController_getFeatures` is reachable as:

```
resource://AppController_getFeatures
```

---

## Video upload

`POST /videos` is intentionally **not** exposed.  Video upload is a long-running,
multipart operation better handled directly via the VSS REST API.  Use the MCP
server for discovery, search, status, and summary workflows only.

---

## Connecting with MCP Inspector

```bash
npx -y @modelcontextprotocol/inspector
```

1. Select **Streamable HTTP** transport
2. Enter `http://localhost:8000/mcp`
3. Click **Connect**

Inspector lists all tools and resources registered for the active filter.  Use
the **Run tool** button to call a tool and confirm the MCP server can reach the
VSS backend.

---

## Filter file format

Each filter file is a JSON object:

```json
{
  "enabled": true,
  "server_name": "vss_search_mcp",
  "tool_prefix": "vss",
  "resource_scheme": "vss",
  "apis": {
    "GET /app/features": { "expose": "resource" },
    "POST /search/query": {
      "expose": "tool",
      "tool_name": "run_search_query"
    },
    "DELETE /tags/{tagId}": {
      "expose": "tool",
      "tool_name": "delete_tag",
      "description": "Remove a tag from the VSS index."
    }
  }
}
```

| Field            | Description                                                                     |
|------------------|---------------------------------------------------------------------------------|
| `enabled`        | Set to `false` to disable the server without removing the config                |
| `server_name`    | MCP server name reported to clients                                             |
| `tool_prefix`    | Prefix prepended to every `tool_name` (e.g. `"vss"` → `"vss_run_search_query"`)|
| `resource_scheme`| Reserved for future use; does not affect resource URIs in the current version   |
| `apis`           | Map of `"METHOD /path"` → exposure config                                       |

Exposure values for `expose`:

- `"tool"` — registered as an MCP tool; `tool_name` is **required**
- `"resource"` — registered as a read-only MCP resource (GET only)
- `"disabled"` — explicitly excluded from the MCP surface

Any endpoint **not listed** in `apis` is automatically excluded.

---

## Adding a new endpoint

1. Open the relevant filter file (or create a new one).
2. Add a `"METHOD /path"` entry under `"apis"` with the desired `expose` value.
3. Restart the container — the server re-reads the spec and filter on each start.

No code changes are needed.

---

## Project structure

```
mcp/
├── main.py              # Convenience entry point (delegates to src/main.py)
├── pyproject.toml       # Project metadata and dependencies (uv-managed)
├── uv.lock              # Locked dependency tree
├── Dockerfile
├── all.json             # Filter: all VSS endpoints (default)
├── search.json          # Filter: search-only endpoints
├── summary.json         # Filter: summary-only endpoints
│
├── src/
│   ├── main.py          # Server bootstrap: loads spec, filter → FastMCP.from_openapi()
│   ├── core/
│   │   ├── config.py    # Settings, env parsing, path resolution
│   │   └── logging.py   # Logging setup
│   └── filters/
│       └── config.py    # ProxyFilterConfig, ApiConfig, filter helpers
│
└── tests/
    ├── test_config.py   # Settings and environment parsing tests
    └── test_filters.py  # Filter config validation tests
```

---

## How it works

1. **Spec fetch** — on startup, the server GETs the VSS OpenAPI JSON from
   `API_SPEC_URL`.
2. **Filter load** — the filter file is read and validated.
3. **Route mapping** — for every operation in the spec, the server checks the
   filter: expose as `tool`, `resource`, or exclude.
4. **Name mapping** — tool names are resolved to `{tool_prefix}_{tool_name}`
   via the filter's `mcp_names` map.
5. **FastMCP** — `FastMCP.from_openapi()` receives the spec, an
   `httpx.AsyncClient` pointing at `API_BASE_URL`, plus the route and name
   maps.  It handles `$ref` resolution, JSON body flattening, and HTTP↔MCP
   translation transparently.
6. **Serve** — the MCP server runs on streamable HTTP at `MCP_HOST:MCP_PORT/MCP_PATH`.
