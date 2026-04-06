# VSS MCP Server

This project is a real MCP server built with the official [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk). It exposes a curated subset of the Open Edge Platform Video Search and Summarization (VSS) REST API as **MCP tools** and **MCP resources** so agent clients can connect over **streamable HTTP** and use the VSS backend without speaking the REST API directly.

The supported backend operations were derived from `../docs/user-guide/_assets/vss-api.yaml`.

Media upload is intentionally **not proxied through MCP**. Agents should upload videos or images directly to the VSS backend `POST /videos` endpoint, then use this MCP server for inspection, search, and follow-up actions.

## What this server exposes

### Tools

| Tool | Backing VSS endpoint | Notes |
| --- | --- | --- |
| `vss_get_app_config` | `GET /app/config` | Read-only |
| `vss_get_app_features` | `GET /app/features` | Read-only |
| `vss_list_tags` | `GET /tags` | Read-only |
| `vss_delete_tag` | `DELETE /tags/{tagId}` | Destructive |
| `vss_get_video` | `GET /videos/{videoId}` | Can optionally include binary content as base64 |
| `vss_list_videos` | `GET /videos` | Read-only |
| `vss_create_video_search_embeddings` | `POST /videos/search-embeddings/{videoId}` | Action |
| `vss_execute_search_query` | `POST /search/query` | Action |

Every tool returns:

- human-readable text content (`response_format="markdown"` by default)
- structured JSON in `structuredContent`

### Resources

| Resource URI | Backing VSS endpoint |
| --- | --- |
| `vss://app/config` | `GET /app/config` |
| `vss://app/features` | `GET /app/features` |
| `vss://tags` | `GET /tags` |
| `vss://videos` | `GET /videos` |
| `vss://videos/{video_id}` | `GET /videos/{videoId}` |
| `vss://help/upload-api` | Static MCP guidance for direct media upload |

Resources are intended for read-only context loading. When a backend response is binary, the resource returns metadata instead of embedding large binary payloads into model context.

### Prompts

| Prompt | Purpose |
| --- | --- |
| `vss_upload_api_help` | Explain the direct VSS upload workflow and the recommended MCP follow-up steps |

## Project structure

```text
mcp/
├── Dockerfile
├── README.md
├── main.py
├── pyproject.toml
├── uv.lock
└── vss_proxy/
    ├── __init__.py
    ├── client.py
    ├── config.py
    ├── formatting.py
    ├── logging_config.py
    ├── main.py
    └── models.py
```

## Requirements

- Python 3.10 or newer
- `uv`
- A reachable VSS backend URL

Dependencies:

- `mcp[cli]`
- `httpx`

## Configuration

The server is configured via environment variables.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `VSS_BASE_URL` | Yes | None | Base URL of the VSS backend |
| `VSS_REQUEST_TIMEOUT` | No | `60` | Outbound request timeout in seconds |
| `VSS_API_TOKEN` | No | None | Optional token injected into outbound `Authorization` headers |
| `VSS_AUTH_SCHEME` | No | `Bearer` | Auth scheme used with `VSS_API_TOKEN` |
| `LOG_LEVEL` | No | `INFO` | Python and MCP server log level |
| `MCP_HOST` | No | `127.0.0.1` | Bind address for the MCP server |
| `MCP_PORT` | No | `8000` | Listening port |
| `MCP_PATH` | No | `/mcp` | Streamable HTTP endpoint path |
| `MCP_STATELESS_HTTP` | No | `true` | Enable stateless streamable HTTP responses |

For local-only development, keep `MCP_HOST=127.0.0.1`. For container or remote deployment, set `MCP_HOST=0.0.0.0`.

## Setup

```bash
cd sample-applications/video-search-and-summarization/mcp
uv sync
```

## Running the MCP server

```bash
VSS_BASE_URL=http://localhost:8000 uv run vss-mcp
```

The streamable HTTP transport is available at:

```text
http://localhost:8000/mcp
```

## Connecting agent clients

### GitHub Copilot CLI

```bash
copilot
```

Inside the interactive Copilot CLI session, add the server with:

```text
/mcp add
```

Use these values in the form:

| Field | Value |
| --- | --- |
| Name | `vss-mcp` |
| Transport | `http` |
| URL | `http://localhost:8000/mcp` |

Press `Ctrl+S` to save the server configuration.

Copilot CLI stores MCP server definitions in `~/.copilot/mcp-config.json` by default. You can change the base config directory with the `COPILOT_HOME` environment variable.

After saving, ask Copilot to use the server naturally or inspect the configured servers with:

```text
/mcp
```

### MCP Inspector

```bash
npx -y @modelcontextprotocol/inspector
```

Then connect the inspector UI to `http://localhost:8000/mcp`.

## Example usage patterns

- Load context with the `vss://app/config` resource.
- Read `vss://help/upload-api` or invoke `vss_upload_api_help` when an agent needs upload instructions.
- Execute search with `vss_execute_search_query`.
- Upload media directly to `POST {VSS_BASE_URL}/videos`.
- After direct upload, use `vss_list_videos`, `vss_get_video`, and `vss_create_video_search_embeddings`.

## Direct upload guidance for agents

The MCP server instructions explicitly tell clients not to upload through MCP. Instead, agents should call the VSS backend directly:

```text
POST {VSS_BASE_URL}/videos
Content-Type: multipart/form-data
```

Multipart fields:

- `video` (required)
- `name` (optional)
- `tags` (optional, comma-separated)

Example:

```bash
curl -X POST "${VSS_BASE_URL}/videos" \
  -F "video=@/path/to/file.mp4" \
  -F "name=Demo clip" \
  -F "tags=demo,test"
```

Inside MCP clients, the same guidance is available through:

- resource: `vss://help/upload-api`
- prompt: `vss_upload_api_help`

## Running with Docker

Build:

```bash
docker build -t vss-mcp-server .
```

Run:

```bash
docker run --rm -p 8000:8000 \
  -e VSS_BASE_URL=http://host.docker.internal:12345/manager \
  vss-mcp-server
```

The container defaults `MCP_HOST=0.0.0.0`, so the MCP endpoint is reachable on `http://localhost:8000/mcp`.

## Extending the server

1. Add a new helper call in `vss_proxy/client.py` only if a new endpoint needs special request handling.
2. Add a tool or resource in `vss_proxy/main.py`.
3. Reuse the shared formatting helpers in `vss_proxy/formatting.py` so new operations keep the same JSON and Markdown result shape.

This keeps transport concerns, backend access, and result rendering separate and makes future endpoint additions straightforward.

## Logging and debugging

- Incoming MCP requests and outbound VSS calls are logged through Python logging.
- Backend connectivity failures are returned as MCP tool errors with actionable messages.
- Backend non-2xx responses are surfaced to the tool caller as structured error results instead of being silently swallowed.

## Notes

- Uploads are intentionally out of band: agents should call the VSS backend directly rather than routing media through this MCP server.
- Saved-search CRUD and listing are intentionally omitted; use `vss_execute_search_query` for search requests.
- `vss_get_video(include_binary_content=true)` returns base64 when the backend responds with binary data. The default behavior omits large binary payloads from tool results and returns metadata instead.
- This server intentionally exposes only the requested subset of VSS endpoints.
