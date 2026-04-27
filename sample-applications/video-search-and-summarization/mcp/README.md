# Video Search and Summarization MCP Server

This is the **MCP (Model Context Protocol) server** for the
[Video Search and Summarization (VSS)](https://github.com/open-edge-platform/edge-ai-libraries)
sample application. It proxies VSS REST endpoints to MCP clients (agents, IDE
extensions, MCP Inspector, …) as **tools** and **resources**, using the
[`fastmcp`](https://gofastmcp.com) library to translate the live VSS OpenAPI
spec into an MCP surface at startup.

> **Note:** The MCP server currently supports **Search mode** only.
> Summary and combined Search + Summary modes will be supported in a future release.


## Project Structure

```
mcp/                             ← cd here before running any commands
├── pyproject.toml               # Project metadata and dependencies (uv-managed)
├── uv.lock                      # Locked dependency tree
├── Dockerfile
├── all.json                     # Filter: all VSS endpoints (default)
├── search.json                  # Filter: search-only endpoints
├── summary.json                 # Filter: summary-only endpoints
│
├── src/
│   ├── main.py                  # Server bootstrap
│   ├── server.py                # MCP factory and singleton
│   ├── core/
│   │   ├── config.py            # Settings, env parsing, path resolution
│   │   └── logging.py           # Logging setup
│   ├── filters/
│   │   └── config.py            # Filter validation, ProxyFilterConfig, ApiConfig
│   └── openapi/
│       ├── loader.py            # Spec fetching and parsing
│       └── mapping.py           # Route classification, tool/resource naming
│
└── tests/
    ├── test_config.py           # Settings and environment parsing tests
    └── test_filters.py          # Filter config validation tests
```


## How It Works

1. **Spec fetch** : on startup, the server GETs the VSS OpenAPI JSON from `API_SPEC_URL`.
2. **Filter load** : the filter file is read and validated.
3. **Route mapping** : for every operation in the spec, the server checks the
   filter: expose as `tool`, `resource`, or exclude.
4. **Name mapping** : tool names are resolved to `{prefix}_{tool_name}` and
   resource names to `{prefix}_{resource_name}`.
5. **Serve** : the MCP server runs on streamable HTTP at `MCP_HOST:MCP_PORT/MCP_PATH`.


## Quick start

All commands below assume you are in the `mcp/` directory:

```bash
cd sample-applications/video-search-and-summarization/mcp
```

**Build the image:**

```bash
docker build -t vss-mcp .
```

**Run against a VSS Search backend:**

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)/search.json:/app/search.json:ro" \
  -e API_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
  -e API_BASE_URL=http://<VSS_IP>:12345/manager \
  -e FILTER_FILE_PATH=/app/search.json \
  vss-mcp
```

The MCP server is then reachable at `http://127.0.0.1:8000/mcp`.

See [docs/user-guide/mcp-server.md](../docs/user-guide/mcp-server.md) for the
full guide, runtime configuration, filter file format, and how to extend the server.


## Filter File Format

Each filter file is a JSON object:

```json
{
  "enabled": true,
  "server_name": "vss_search_mcp",
  "prefix": "vss",
  "apis": {
    "GET /app/features": { "expose": "resource", "resource_name": "app_features" },
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

| Field         | Description                                                                              |
|---------------|------------------------------------------------------------------------------------------|
| `enabled`     | Set to `false` to disable the server without removing the config                         |
| `server_name` | MCP server name reported to clients                                                      |
| `prefix`      | Prefix applied to every tool and resource name (e.g. `"vss"` → `"vss_run_search_query"`) |
| `apis`        | Map of `"METHOD /path"` → exposure config                                                |

Exposure values for `expose`:

- `"tool"` : registered as an MCP tool; `tool_name` is **required**
- `"resource"` : registered as a read-only MCP resource (GET only); `resource_name` is **required**
- `"disabled"` : explicitly excluded from the MCP surface

Each endpoint entry can optionally include a `description` field to override the OpenAPI description.

Any endpoint **not listed** in `apis` is automatically excluded.


## Adding a New Endpoint

1. Open the relevant filter file (or create a new one) in the `mcp/` directory.
2. Add a `"METHOD /path"` entry under `"apis"` with the desired `expose` value.
3. Restart the container, the server re-reads the spec and filter on each start.

No code changes are needed.

