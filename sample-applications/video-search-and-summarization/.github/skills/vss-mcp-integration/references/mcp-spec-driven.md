# VSS MCP spec-driven FastMCP proxy reference

This reference is grounded in `sample-applications/video-search-and-summarization/mcp`.

## Actual architecture

The MCP package is a Poetry project named `mcp-app` (`mcp/pyproject.toml`) with runtime dependencies `fastmcp`, `httpx`, and `pydantic`. The console script is:

```toml
[tool.poetry.scripts]
mcp-app = "src.main:main"
```

`mcp/src/__init__.py` re-exports `main`, `create_mcp`, and `get_mcp`.

`mcp/src/main.py` runs FastMCP with streamable HTTP:

```python
server.run(
    transport="streamable-http",
    host=settings.mcp_host,
    port=settings.mcp_port,
    path=settings.mcp_path,
    stateless_http=settings.stateless_http,
    log_level=settings.log_level,
)
```

`mcp/src/server.py` builds the server from the live OpenAPI document and the JSON filter:

- `fetch_openapi_spec(settings.spec_url, settings.request_timeout_seconds)` downloads JSON from `API_SPEC_URL` using `urllib.request.urlopen`.
- `httpx.AsyncClient(base_url=settings.api_base_url, timeout=...)` forwards tool calls to `API_BASE_URL`.
- `FastMCP.from_openapi(openapi_spec=spec, client=client, name=filter_config.server_name, mcp_names=..., route_map_fn=..., mcp_component_fn=...)` generates MCP components.

The proxy does not hand-code VSS tools. It lets FastMCP derive schemas from the live OpenAPI spec, then applies filter-driven names/classification/descriptions.

## Runtime configuration keys

From `mcp/src/core/config.py`:

| Env var | Required | Default | Behavior |
|---|---:|---|---|
| `API_SPEC_URL` | yes | none | URL to OpenAPI/Swagger JSON; stripped, must be non-empty. |
| `API_BASE_URL` | yes | none | REST base URL; stripped and trailing slash removed. |
| `FILTER_FILE_PATH` | yes | none | Filesystem path to filter JSON; must exist. |
| `REQUEST_TIMEOUT` | no | `60.0` | Positive float; used for spec fetch and proxied requests. |
| `LOG_LEVEL` | no | `INFO` | Uppercased Python logging level. |
| `MCP_HOST` | no | `0.0.0.0` | Bind address. |
| `MCP_PORT` | no | `8000` | Integer in `1..65535`. |
| `MCP_PATH` | no | `/mcp` | Normalized to start with `/`. |
| `MCP_STATELESS_HTTP` | no | `true` | Boolean: `true/false`, `yes/no`, `on/off`, `1/0`. |

Although `DEFAULT_FILTER_CONFIG_PATH = "all.json"` exists, current settings parsing still requires `FILTER_FILE_PATH` to be set and to point to an existing file.

## Compose and Docker behavior

`mcp/Dockerfile` builds a Python 3.12 slim image, installs Poetry 2.4.1, installs main dependencies, exposes port `8000`, and starts `CMD ["mcp-app"]`.

`mcp/compose.yaml` defines:

- `mcp-server`, container `vss-mcp-server`, host networking, `FILTER_FILE_PATH=${FILTER_FILE_PATH:-/app/search.json}`, volume `./search.json:/app/search.json:ro`, default `MCP_PORT=8000`, `MCP_PATH=/mcp`, `REQUEST_TIMEOUT=60`, `LOG_LEVEL=INFO`.
- `mcp-inspector`, image `ghcr.io/modelcontextprotocol/inspector:0.21.2-hotfix-3`, host networking, default client port `6274`.

`.env.example` sets:

```dotenv
VSS_IP=<VSS_IP>
HOST_IP=<HOST_IP>
API_SPEC_URL=http://${VSS_IP}:12345/manager/swagger/json
API_BASE_URL=http://${VSS_IP}:12345/manager
FILTER_FILE_PATH=/app/search.json
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_PATH=/mcp
REQUEST_TIMEOUT=60
LOG_LEVEL=INFO
INSPECTOR_CLIENT_PORT=6274
DANGEROUSLY_OMIT_AUTH=true
```

The compose file appends `${VSS_IP}` to `no_proxy` / `NO_PROXY` so the server can reach the backend directly in proxied environments.

## Filter file schema

The filter file is parsed by `mcp/src/filters/config.py` into `ProxyFilterConfig`:

```json
{
  "server_name": "vss_search_mcp",
  "prefix": "vss",
  "apis": {
    "METHOD /path": {
      "type": "tool",
      "name": "identifier_suffix",
      "description": "Optional override prepended to OpenAPI description."
    }
  }
}
```

Top-level fields:

- `server_name`: FastMCP server name shown to clients. Defaults to `app_proxy_mcp` if omitted. Normalized: strip, lowercase, replace `-` with `_`; must match identifier pattern `^[A-Za-z_][A-Za-z0-9_]*$`.
- `prefix`: prefix used in final MCP component names. Defaults to `api` if omitted. Same normalization/validation as `server_name`.
- `apis`: explicit allow-list keyed by canonical `"METHOD /path"`. Operations not listed are excluded.

Per-API fields:

- `type`: required; only `"tool"` or `"resource"`.
- `name`: required; stripped and must be an identifier. Final MCP name is `f"{prefix}_{name}"`.
- `description`: optional; trimmed; all-whitespace becomes absent. If present, `build_component_fn()` prepends it to FastMCP's generated description.

Validation rules from tests and code:

- Keys are normalized to one space and uppercase method (`"  get   /widgets  "` -> `"GET /widgets"`).
- Supported methods are `GET`, `PUT`, `POST`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`.
- Wildcards `*` and `?` in paths are rejected. List every endpoint explicitly.
- Duplicate normalized API keys are rejected.
- Duplicate `name` values are rejected across all tools/resources because the namespace is shared under one prefix.
- Resources must be GET-only.
- Extra fields are forbidden; stale schemas using `expose`, `tool_name`, or `resource_name` fail validation.

## Bundled `search.json`

`mcp/search.json` is the Search-mode filter:

| Final MCP name | Type | REST endpoint |
|---|---|---|
| `vss_health` | resource | `GET /health` |
| `vss_app_features` | resource | `GET /app/features` |
| `vss_get_tags` | tool | `GET /tags` |
| `vss_delete_tag` | tool | `DELETE /tags/{tagId}` |
| `vss_get_all_videos` | tool | `GET /videos` |
| `vss_get_video` | tool | `GET /videos/{videoId}` |
| `vss_create_video_search_embeddings` | tool | `POST /videos/search-embeddings/{videoId}` |
| `vss_run_search_query` | tool | `POST /search/query` |

The user guide says `POST /videos` is intentionally not exposed because video upload is a long-running multipart operation and should be handled through VSS REST directly.

## How spec routes become MCP components

`mcp/src/openapi/mapping.py` builds three callbacks for `FastMCP.from_openapi`.

### `build_mcp_names(spec, filter_config)`

- Iterates `spec["paths"]`.
- Looks at HTTP method entries only.
- Reads each operation's `operationId`.
- If the exact `(method, path)` is configured in the filter, maps `operationId` to `{prefix}_{name}`.
- If no `operationId` exists, no rename is added. The route may still be classified by `route_map_fn`, but naming will fall back to FastMCP behavior.

### `build_route_map_fn(filter_config)`

For each FastMCP `HTTPRoute`:

- If the exact `METHOD /path` is absent from `apis`, returns `MCPType.EXCLUDE` and increments `excluded`.
- If `type == "tool"`, returns `MCPType.TOOL`.
- If `type == "resource"` and the path contains `{`, returns `MCPType.RESOURCE_TEMPLATE`.
- Otherwise returns `MCPType.RESOURCE`.

This exact-match allow-list is the main reason missing tools can be silent: an endpoint can be present in the OpenAPI spec but excluded because the filter key is absent or slightly different.

### `build_component_fn(filter_config)`

If a filter entry has `description`, it prepends that text to the component description generated from the OpenAPI spec.

## Run and connect procedure

Docker Compose path, matching docs:

```bash
cd sample-applications/video-search-and-summarization/mcp
cp .env.example .env
# edit VSS_IP and HOST_IP; optionally proxies
docker compose up --build -d
```

Connect an MCP client or AI agent using streamable HTTP at:

```text
http://<HOST_IP>:8000/mcp
```

For MCP Inspector:

1. Open `http://<HOST_IP>:6274`.
2. Select **Streamable HTTP**.
3. Enter `http://<HOST_IP>:8000/mcp`.
4. Click **Connect**.

Stop:

```bash
docker compose down
```

Local development run:

```bash
cd sample-applications/video-search-and-summarization/mcp
poetry install
API_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
API_BASE_URL=http://<VSS_IP>:12345/manager \
FILTER_FILE_PATH="$PWD/search.json" \
LOG_LEVEL=DEBUG \
poetry run mcp-app
```

Run tests:

```bash
cd sample-applications/video-search-and-summarization/mcp
poetry run python -m unittest discover tests -v
```

## Worked example: expose an endpoint in a custom filter

Goal: create a small custom filter that exposes `GET /app/features` as a resource and `POST /search/query` as a tool. Both paths are real VSS Search entries already present in `mcp/search.json`; this pattern is the same for any additional endpoint that exists in the live OpenAPI spec.

1. Create `mcp/my-search-filter.json`:

```json
{
  "server_name": "vss_search_mcp",
  "prefix": "vss",
  "apis": {
    "GET /app/features": {
      "type": "resource",
      "name": "app_features",
      "description": "Return enabled VSS features before choosing a workflow."
    },
    "POST /search/query": {
      "type": "tool",
      "name": "run_search_query",
      "description": "Run a natural-language search against indexed videos."
    }
  }
}
```

2. Point the server at it.

For local Poetry:

```bash
FILTER_FILE_PATH="$PWD/my-search-filter.json" poetry run mcp-app
```

Include the other required env vars (`API_SPEC_URL`, `API_BASE_URL`) as shown above.

For Compose, either replace `search.json` or update `.env` and mount the file. Current `compose.yaml` only mounts `./search.json:/app/search.json:ro`, so if `FILTER_FILE_PATH=/app/my-search-filter.json` you must add a matching volume such as `./my-search-filter.json:/app/my-search-filter.json:ro`.

3. Restart and inspect.

Expected names:

- `vss_app_features` as a resource (`resource://vss_app_features`)
- `vss_run_search_query` as a tool

## Debug checklist for "why isn't my MCP tool showing up?"

1. **Spec reachable:** `API_SPEC_URL` must return valid JSON object with `paths`; `fetch_openapi_spec()` raises if unreachable or invalid.
2. **Backend base correct:** `API_BASE_URL` must point at the REST base (`http://<VSS_IP>:12345/manager` in `.env.example`) and has trailing `/` stripped.
3. **Filter path exists in the right filesystem:** container defaults to `/app/search.json`; host path `./search.json` is mounted read-only there.
4. **Exact method/path match:** compare the filter key to the live OpenAPI path exactly. `GET /videos/{videoId}` is different from `GET /videos/{id}`.
5. **No wildcards:** `GET /search/*` is invalid; enumerate routes.
6. **Resource vs tool:** non-GET endpoints cannot be `resource`; use `tool`.
7. **Identifier names:** `name`, `prefix`, `server_name` cannot contain hyphens after per-API `name` validation; top-level hyphens are normalized to underscores.
8. **No duplicates:** two entries with the same `name` under the same `prefix` are rejected.
9. **No stale fields:** remove `expose`, `tool_name`, `resource_name`; only `type`, `name`, `description` are allowed per entry.
10. **Operation IDs:** if a route lacks OpenAPI `operationId`, `build_mcp_names()` cannot rename it to `{prefix}_{name}`.
11. **Logs:** set `LOG_LEVEL=DEBUG`; mapping logs include `[exclude]`, `[tool]`, `[resource]`, `[template]`, and operationId rename details.
12. **Expected exclusions:** endpoints not listed in `apis` are intentionally `MCPType.EXCLUDE`; upload `POST /videos` is intentionally absent by design.
