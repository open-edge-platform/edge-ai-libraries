<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Model Download MCP Server

The Model Download microservice can be deployed as an **MCP (Model Context Protocol) server**, enabling LLM agents (Claude Desktop, GitHub Copilot, custom AI agents) to download, convert, and manage AI models through the standardised MCP interface.

## Quick Start

### Local (without Docker)

#### Install the MCP dependency

```bash
uv sync --extra mcp
```

#### Run the server

```bash
# stdio transport (default — for Claude Desktop, Copilot CLI, local agents)
python -m src.mcp

# HTTP transport (for remote MCP clients)
python -m src.mcp --transport http --port 8080

# FastMCP CLI
fastmcp run src/mcp/server.py:mcp --transport http --port 8080
```

### Container Deployment

The same Docker image supports both REST API and MCP modes. Pass `--mcp` to switch.

#### Using run_service.sh

```bash
# REST API (default)
source scripts/run_service.sh --plugins huggingface,openvino

# MCP server
source scripts/run_service.sh --plugins huggingface,openvino --mcp
```

#### Using Docker Compose directly

```bash
# REST API (default)
docker compose -f docker/compose.yaml up -d

# MCP server (uses the "mcp" profile)
docker compose -f docker/compose.yaml --profile mcp up -d model_download_mcp
```

#### Using Docker run

```bash
docker run -e ENABLED_PLUGINS=all \
  -v ~/models:/opt/models \
  -p 8200:8000 \
  model-download:latest \
  --plugins all --mcp
```

#### Environment Variables for MCP mode

| Variable | Description | Default |
|---|---|---|
| `MCP_TRANSPORT` | Transport protocol (`http` or `stdio`) | `http` |
| `MCP_HOST` | Host to bind (container mode) | `0.0.0.0` |
| `MCP_PORT` | Port for HTTP transport | `8000` |

## Available MCP Tools

| Tool | Description |
|---|---|
| `health_check` | Check service health |
| `download_model` | Submit a model download/conversion job |
| `get_job_status` | Get status of a specific job by ID |
| `list_jobs` | List all jobs |
| `cancel_job` | Cancel a running or queued job |
| `get_model_jobs` | Get all jobs for a specific model name |
| `get_model_results` | Get completed downloads/conversions |
| `list_plugins` | List available plugins and capabilities |
| `list_hub_models` | Browse/search models on a hub |

## Available MCP Resources

| URI | Description |
|---|---|
| `models://jobs` | All job records |
| `models://jobs/{job_id}` | A specific job by ID |
| `models://results` | Completed download/conversion results |
| `models://plugins` | Available plugins and capabilities |

## Client Configuration Examples

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "model-download": {
      "command": "python",
      "args": ["-m", "src.mcp"],
      "cwd": "/path/to/model-download"
    }
  }
}
```

### Remote HTTP Client (Python)

```python
import asyncio
from fastmcp import Client

client = Client("http://localhost:8080/mcp")

async def main():
    async with client:
        # Download a model
        result = await client.call_tool("download_model", {
            "name": "meta-llama/Llama-3.2-1B",
            "hub": "huggingface",
        })
        print(result)

        # Check job status
        status = await client.call_tool("get_job_status", {
            "job_id": "<job-id-from-above>"
        })
        print(status)

asyncio.run(main())
```

## Environment Variables

The MCP server uses the same environment variables as the REST API:

| Variable | Description | Default |
|---|---|---|
| `MODELS_DIR` | Base directory for downloaded models | `/opt/models` |
| `HF_TOKEN` | HuggingFace API token (for gated models) | — |
| `ENABLED_PLUGINS` | Comma-separated list of plugins to activate | `all` |

## REST API vs MCP Server

Both modes share the same core logic (`ModelManager`, `PluginRegistry`). Choose based on your use case:

| | REST API (FastAPI) | MCP Server |
|---|---|---|
| **Use when** | Building web apps, CI/CD pipelines | LLM agent integration |
| **Transport** | HTTP REST | stdio or Streamable HTTP |
| **Client** | Any HTTP client | MCP-compatible LLM client |
| **Run command** | `uvicorn src.api.main:app` | `python -m src.mcp` |
