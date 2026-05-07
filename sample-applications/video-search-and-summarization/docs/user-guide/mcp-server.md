# MCP Server for VSS

The VSS MCP server exposes the [Video Search and Summarization (VSS)](./index.md) REST API to AI agents and IDE extensions using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). It reads the live VSS OpenAPI spec at startup and registers a selected subset of endpoints as **MCP tools** and **resources**.

> **Note:** The MCP server currently supports **Search mode** only.
> Summary and combined Search + Summary modes will be supported in a future release.

The server is controlled by a **filter file**, a small JSON document that lists exactly which VSS endpoints to expose and whether each appears as a tool or a resource. The bundled `search.json` filter covers the Search mode:


## Prerequisites

- The **VSS application must be running and reachable** before starting this server.
- Docker and Docker Compose installed ([Installation Guide](https://docs.docker.com/get-docker/)).
- Network access from the machine running this container to the VSS host.

## Quick Start

Navigate to the `mcp/` directory first, all commands below assume you are there:

```bash
cd sample-applications/video-search-and-summarization/mcp
```

Docker Compose builds the MCP server and starts [MCP Inspector](https://github.com/modelcontextprotocol/inspector) alongside it for interactive testing and debugging.

1. **Create your `.env` file:**

   ```bash
   cp .env.example .env
   ```

2. **Edit `.env`** — set the VSS backend IP and HOST IP:

   ```dotenv
   VSS_IP=<your-vss-ip>
   HOST_IP=<your-host-ip>
   ```

   > **Note:** The `VSS_IP` variable is automatically appended to `no_proxy` inside the containers by `compose.yaml`, so the MCP server can always reach the VSS backend directly without going through the proxy.

3. **Build and start:**

   ```bash
   docker compose up --build -d
   ```

4. **Access the services:**

   | Service        | URL                              | Description                        |
   |----------------|----------------------------------|------------------------------------|
   | MCP Server     | `http://<HOST_IP>:8000/mcp`      | Streamable HTTP MCP endpoint       |
   | MCP Inspector  | `http://<HOST_IP>:6274`          | Web UI for testing the MCP server  |

5. **Connect Inspector to MCP Server:**
   - Open `http://<HOST_IP>:6274` in your browser.
   - Select **Streamable HTTP** transport.
   - Enter `http://<HOST_IP>:8000/mcp` as the URL.
   - Click **Connect**.

6. **Stop:**

   ```bash
   docker compose down
   ```


## Runtime Configuration

| Variable                    | Required          | Default            | Description                                           |
|-----------------------------|-------------------|--------------------|-------------------------------------------------------|
| `API_SPEC_URL`              | **Yes**           | -                 | URL to the VSS OpenAPI/Swagger JSON document          |
| `API_BASE_URL`              | **Yes**           | -                  | Base URL of the running VSS REST service              |
| `FILTER_FILE_PATH`          | **Yes**           | -                  | Path to the filter config file inside the container   |
| `REQUEST_TIMEOUT`           | No                | `60`               | Outbound request timeout in seconds                   |
| `LOG_LEVEL`                 | No                | `INFO`             | Python log level (`DEBUG`, `INFO`, `WARNING`, …)      |
| `MCP_HOST`                  | No                | `0.0.0.0`          | Bind address                                          |
| `MCP_PORT`                  | No                | `8000`             | Listening port                                        |
| `MCP_PATH`                  | No                | `/mcp`             | Streamable HTTP endpoint path                         |



## What MCP Clients See

At startup the server reads the VSS OpenAPI spec and the filter file, then registers exactly the operations listed in the filter.

**Tools** (state-changing or parameterised operations), examples from `search.json`:

| Tool name                            | VSS endpoint                                   |
|--------------------------------------|------------------------------------------------|
| `vss_run_search_query`               | `POST /search/query`                           |
| `vss_get_all_videos`                 | `GET /videos`                                  |
| `vss_get_video`                      | `GET /videos/{videoId}`                        |
| `vss_create_video_search_embeddings` | `POST /videos/search-embeddings/{videoId}`     |
| `vss_get_tags`                       | `GET /tags`                                    |
| `vss_delete_tag`                     | `DELETE /tags/{tagId}`                         |

Tool names are built from `prefix` + `name` in the filter file, forming names like `"vss_run_search_query"`.

**Resources** (read-only, GET only) are named from `prefix` + `name` in the filter file. For example, a resource with `prefix: "vss"` and `name: "app_features"` is reachable as:

```
resource://vss_app_features
```

## Video Upload

`POST /videos` is intentionally **not** exposed. Video upload is a long-running multipart operation better handled directly via the VSS REST API. Use the MCP server for discovery, search and status workflows only.
