# Video Search and Summarization MCP Server

This directory contains the FastMCP server for the **Video Search and Summarization (VSS)** sample application. It connects MCP clients to the running VSS REST service and exposes only the VSS capabilities selected by the loaded filter file.

Provide a reachable VSS OpenAPI/Swagger URL at runtime, then use one of the bundled VSS mode filters:

- three bundled VSS mode filters:
  - `./proxy-search.json`
  - `./proxy-summary.json`
  - `./proxy-all.json`

Use the filter that matches the VSS backend you started:

| VSS deployment mode | Filter file |
| --- | --- |
| Search only | `./proxy-search.json` |
| Summary only | `./proxy-summary.json` |
| Search + Summary | `./proxy-all.json` |

`proxy-all.json` is the default when `APP_PROXY_FILTER_PATH` is not set.

## Prerequisite

Before starting this MCP server, the **Video Search and Summarization application must already be up and running**.

Make sure:

1. the VSS application is already running
2. the VSS REST endpoint is reachable from the machine where Docker runs
3. you know the base URL, for example `http://<VSS_IP>:12345/manager`

## Quick start

Build the image from this `mcp/` directory:

```bash
docker build -t vss-mcp .
```

Run it against a VSS backend:

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)/proxy-all.json:/app/proxy-all.json:ro" \
  -e APP_PROXY_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
  -e TARGET_BASE_URL=http://<VSS_IP>:12345/manager \
  -e APP_PROXY_FILTER_PATH=/app/proxy-search.json \
  vss-mcp
```

That starts the MCP server on:

```text
http://127.0.0.1:8000/mcp
```

## Select the right VSS mode

Point the MCP server at the filter that matches the VSS backend mode:

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)/proxy-search.json:/app/proxy-search.json:ro" \
  -e APP_PROXY_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
  -e TARGET_BASE_URL=http://<VSS_IP>:12345/manager \
  -e APP_PROXY_FILTER_PATH=/app/proxy-search.json \
  vss-mcp
```

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)/proxy-summary.json:/app/proxy-summary.json:ro" \
  -e APP_PROXY_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
  -e TARGET_BASE_URL=http://<VSS_IP>:12345/manager \
  -e APP_PROXY_FILTER_PATH=/app/proxy-summary.json \
  vss-mcp
```

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)/proxy-all.json:/app/proxy-all.json:ro" \
  -e APP_PROXY_SPEC_URL=http://<VSS_IP>:12345/manager/swagger/json \
  -e TARGET_BASE_URL=http://<VSS_IP>:12345/manager \
  -e APP_PROXY_FILTER_PATH=/app/proxy-all.json \
  vss-mcp
```

Use the matching filter. For example, if the VSS backend is running in search-only mode, start the MCP server with `proxy-search.json` so summary-only endpoints are not exposed to clients.

## Video upload behavior

The bundled VSS MCP surface intentionally does **not** expose `POST /videos` as an MCP tool.

Use:

1. the direct VSS REST upload API for video upload
2. the MCP server for discovery, search, status, summary, and other supported VSS flows

The built-in guidance resource is available at:

```text
vss://__meta/guidance
```

## Docker notes

For search-only or summary-only VSS deployments, either:

1. mount the matching filter file to `/app/proxy-all.json`, or
2. mount it elsewhere and set `APP_PROXY_FILTER_PATH` to that mounted path

The image does not bake in the filter files. Provide the filter file with a bind mount, and provide the API spec with `APP_PROXY_SPEC_URL`.

## Runtime configuration

Most VSS runs need `APP_PROXY_SPEC_URL`, `TARGET_BASE_URL`, and, when needed, `APP_PROXY_FILTER_PATH`.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `TARGET_BASE_URL` | Yes in normal VSS runs | None | Base URL for the running VSS REST service |
| `APP_PROXY_SPEC_URL` | Yes | None | Remote OpenAPI/Swagger URL |
| `APP_PROXY_FILTER_PATH` | No | bundled `proxy-all.json` | VSS mode filter file |
| `APP_PROXY_REQUEST_TIMEOUT` | No | `60` | Outbound request timeout in seconds |
| `LOG_LEVEL` | No | `INFO` | Python and MCP server log level |
| `MCP_HOST` | No | `127.0.0.1` | Bind address |
| `MCP_PORT` | No | `8000` | Listening port |
| `MCP_PATH` | No | `/mcp` | Streamable HTTP endpoint path |
| `MCP_STATELESS_HTTP` | No | `true` | Enable stateless streamable HTTP responses |

Relative paths are resolved against the current working directory first, then against the project root.

## What MCP clients will see

The server exposes VSS operations as MCP tools and read-only VSS resources.

Examples include:

- tools such as `vss_app_controller_get_features`, `vss_search_controller_get_queries`, and `vss_summary_controller_start_summary_pipeline`
- resources such as `vss://app/config`, `vss://videos`, and `vss://summary/{state_id}`

Metadata resources are always available:

- `vss://__meta/catalog`
- `vss://__meta/filter`
- `vss://__meta/guidance`

## Connecting clients

### MCP Inspector

Use MCP Inspector to verify that the VSS MCP server is reachable and to inspect the generated tools and resources before connecting an agent client.

```bash
npx -y @modelcontextprotocol/inspector
```

When Inspector opens in the browser:

1. select **Streamable HTTP** as the transport
2. enter the MCP server URL:

   ```text
   http://localhost:8000/mcp
   ```

3. click **Connect**

After the connection succeeds, Inspector shows the MCP server metadata and the VSS tools and resources exposed by the running backend.

#### What to inspect

1. **Tools** - review generated tools such as `vss_app_controller_get_features`, `vss_search_controller_get_queries`, and summary tools when summary mode is enabled
2. **Resources** - inspect resources such as `vss://app/config`, `vss://videos`, `vss://__meta/catalog`, `vss://__meta/filter`, and `vss://__meta/guidance`
3. **Tool schema** - open a tool to see the supported arguments, body fields, and other inputs generated from the VSS OpenAPI spec
4. **Run tool** - invoke a tool from Inspector to confirm the MCP server can reach the VSS backend and return data
5. **Read resource** - open a resource URI to verify the resource is available in the active VSS mode

If Inspector cannot connect at all, first check that the Docker container is running and that `http://localhost:8000/mcp` is reachable.

## Notes

Under the hood, this VSS MCP server is implemented with a spec-driven registration layer and JSON mode filters. 
That generic machinery is useful for extension, but the intended day-to-day use in this folder is running the MCP server alongside the Video Search and Summarization sample application.
