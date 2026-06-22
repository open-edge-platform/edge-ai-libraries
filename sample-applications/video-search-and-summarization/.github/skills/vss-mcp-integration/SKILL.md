---
name: vss-mcp-integration
description: Helps developers configure and extend the Video Search and Summarization sample app's spec-driven FastMCP proxy for VSS search. Use when the user wants to connect an AI agent to VSS search, add an MCP tool to VSS, configure the VSS MCP server / filters, run the FastMCP proxy, or debug why isn't my MCP tool showing up.
---

# VSS MCP Integration

Use this for `sample-applications/video-search-and-summarization/mcp`: the Search-mode MCP server that proxies selected VSS REST endpoints to agents via FastMCP.

## Ground truth files

Read these before changing behavior: `mcp/src/server.py`, `mcp/src/core/config.py`, `mcp/src/filters/config.py`, `mcp/src/openapi/{loader.py,mapping.py}`, `mcp/search.json`, `mcp/compose.yaml`, `mcp/.env.example`, `mcp/README.md`, `docs/user-guide/mcp-server.md`, and `mcp/tests/*`.

## How the proxy works

Startup path: `src.main:main` calls `get_settings()`, `get_mcp()`, then `server.run(transport="streamable-http", host=MCP_HOST, port=MCP_PORT, path=MCP_PATH, stateless_http=MCP_STATELESS_HTTP)`.

`create_mcp()` in `mcp/src/server.py`:
1. reads env into `Settings`;
2. loads `FILTER_FILE_PATH` with `load_filter_config()`;
3. fetches the live VSS OpenAPI/Swagger JSON from `API_SPEC_URL`;
4. creates an `httpx.AsyncClient(base_url=API_BASE_URL)`;
5. calls `FastMCP.from_openapi(...)` with:
   - `mcp_names=build_mcp_names(spec, filter_config)`
   - `route_map_fn=build_route_map_fn(filter_config)`
   - `mcp_component_fn=build_component_fn(filter_config)`

The filter is allow-list based. Operations not listed in `apis` are mapped to `MCPType.EXCLUDE`. This spec-driven design is why a path/method mismatch can look like a missing tool: the OpenAPI route is simply excluded rather than treated as an error.

## Run and connect

From `mcp/`:

```bash
cp .env.example .env
docker compose up --build -d
```

Edit `VSS_IP` and `HOST_IP` first. Defaults: MCP server `http://<HOST_IP>:8000/mcp`; Inspector `http://<HOST_IP>:6274`. In Inspector, choose **Streamable HTTP** and connect to the MCP URL.

For local Poetry runs, set all required env vars explicitly:

```bash
cd sample-applications/video-search-and-summarization/mcp
API_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
API_BASE_URL=http://<VSS_IP>:12345/manager \
FILTER_FILE_PATH="$PWD/search.json" \
poetry run mcp-app
```

## Real config keys

Required by `mcp/src/core/config.py`: `API_SPEC_URL`, `API_BASE_URL`, `FILTER_FILE_PATH`.

Optional: `REQUEST_TIMEOUT` default `60`, `LOG_LEVEL` default `INFO`, `MCP_HOST` default `0.0.0.0`, `MCP_PORT` default `8000`, `MCP_PATH` default `/mcp`, `MCP_STATELESS_HTTP` default `true`.

Compose also uses `VSS_IP`, `HOST_IP`, `INSPECTOR_CLIENT_PORT`, `DANGEROUSLY_OMIT_AUTH`, `MCP_PROXY_AUTH_TOKEN`, and proxy vars.

## Add or filter a tool/resource

Edit `mcp/search.json` or point `FILTER_FILE_PATH` to another JSON file. Format:

```json
{
  "server_name": "vss_search_mcp",
  "prefix": "vss",
  "apis": {
    "POST /search/query": {
      "type": "tool",
      "name": "run_search_query",
      "description": "Execute an immediate natural-language search."
    }
  }
}
```

Rules from `mcp/src/filters/config.py`:
- API keys must be exact canonical `"METHOD /path"` entries matching the OpenAPI path, e.g. `"GET /videos/{videoId}"`.
- Supported methods: `GET`, `PUT`, `POST`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`; wildcards are rejected.
- `type` is only `"tool"` or `"resource"`; resources must be `GET`.
- `name`, `prefix`, and `server_name` must be valid identifiers; final names are `{prefix}_{name}`.
- Duplicate `name` values are rejected across tools/resources.
- Unknown fields such as old `expose` / `tool_name` are rejected.

Restart the MCP server after changing the filter; it reads the spec and filter at startup.

## Debug missing tools

1. Confirm the backend and spec URL work: `API_SPEC_URL` must return JSON with `paths`.
2. Confirm `FILTER_FILE_PATH` exists inside the process/container. Compose mounts `./search.json` to `/app/search.json`.
3. Compare the filter key with the live spec exactly: method and path must match, including `{param}` names.
4. Check the endpoint has an OpenAPI `operationId`; `build_mcp_names()` only renames filtered operations with operation IDs.
5. Check filter validation: resource on non-GET, duplicate names, invalid identifiers, wildcards, or extra fields fail startup.
6. Run with `LOG_LEVEL=DEBUG` to see `[exclude]`, `[tool]`, `[resource]`, and rename logs from `mcp/src/openapi/mapping.py`.
7. Remember `POST /videos` is intentionally not exposed in the user guide; uploads should use the REST API directly.

See [references/mcp-spec-driven.md](references/mcp-spec-driven.md) for the detailed spec/filter model and an example.
