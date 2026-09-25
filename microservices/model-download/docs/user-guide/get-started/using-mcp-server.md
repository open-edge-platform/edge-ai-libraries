<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Model Download MCP Server

Every Model Download deployment exposes an **MCP (Model Context Protocol) server** at `/mcp` alongside the REST API. LLM agents (Claude Desktop, GitHub Copilot, and custom AI agents) can therefore download, convert, and manage AI models through MCP without deploying a second service.

## Quick Start

### Local (without Docker)

#### Install dependencies

```bash
uv sync
```

#### Run only the MCP server

```bash
# stdio transport (default — for Claude Desktop, Copilot CLI, local agents)
uv run python -m src.mcp

# HTTP transport (for remote MCP clients)
uv run python -m src.mcp --transport http --port 8080

# FastMCP CLI
uv run fastmcp run src/mcp/server.py:mcp --transport http --port 8080
```

#### Using run_service.sh

```bash
# REST API and MCP server
source scripts/run_service.sh --plugins huggingface,openvino
```
Connect remote MCP clients to `http://localhost:8200/mcp`.

### Container Deployment

The default container serves both interfaces on the same port:

| Interface | Default URL |
|---|---|
| REST API | Existing REST endpoints on `http://localhost:8200` |
| MCP server | `http://localhost:8200/mcp` |

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
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/model-download",
        "python",
        "-m",
        "src.mcp"
      ]
    }
  }
}
```

### GitHub Copilot

Add to `~/.copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "model-download": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/model-download",
        "python",
        "-m",
        "src.mcp"
      ],
      "tools": ["*"]
    }
  }
}
```

***Use an absolute project path. MCP clients execute `command` directly, so shell
operators such as `cd` and `|` must not be included in `args`. The standalone
server writes application logs to stderr to keep stdout reserved for stdio
JSON-RPC messages.***

## Verify the MCP Connection

After adding or changing the configuration, restart the MCP client or reload
its MCP servers. Then use the client's tool view or chat interface to perform
these checks:

1. Confirm that the `model-download` server is connected and exposes the nine
  tools listed in [Available MCP Tools](#available-mcp-tools).
2. Ask the client to call `health_check` from the `model-download` server.
  A working server returns:

  ```json
  {"status": "ok"}
  ```

3. Ask the client to call `list_plugins`. Check that `available_count` is
  greater than zero and that the required hub has `"available": true`.
4. Optionally call `list_jobs`. A new installation normally returns an empty
  list:

  ```json
  {"jobs": []}
  ```

For example, in GitHub Copilot chat, ask:

```text
Use the model-download MCP server to run health_check, then list the available plugins.
```

### End-to-End Download Check

This check requires network access and an available `huggingface` plugin. It
downloads a small test model into `MODELS_DIR`:

1. Call `download_model` with:

  ```json
  {
    "name": "hf-internal-testing/tiny-random-bert",
    "hub": "huggingface",
    "download_path": "mcp-smoke-test"
  }
  ```

2. Copy a returned ID from `job_ids` and call `get_job_status` with:

  ```json
  {"job_id": "<returned-job-id>"}
  ```

3. Poll `get_job_status` until the status is `completed` or `failed`. On
  success, call `get_model_results` and verify that the model path exists
  under `MODELS_DIR/mcp-smoke-test`.

If the server does not connect, run the configured `uv run --directory ...`
command in a terminal to expose startup errors. If health succeeds but a model
operation fails, use `list_plugins` to check plugin activation and availability,
then inspect the error returned by `get_job_status`.

### Remote HTTP Client (Python)

```python
import asyncio
from fastmcp import Client

client = Client("http://localhost:8200/mcp")

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
| `MODELS_DIR` | Base directory for downloaded models | `./models` locally; `/opt/models` in the container |
| `HF_TOKEN` | HuggingFace API token (for gated models) | — |
| `ENABLED_PLUGINS` | Comma-separated list of plugins to activate | `all` |

## REST API vs MCP Server

Both modes share the same core logic (`ModelManager`, `PluginRegistry`). Choose based on your use case:

| | Default deployment | Standalone MCP |
|---|---|---|
| **Use when** | Applications need REST and MCP | An MCP client needs only MCP |
| **Transport** | REST and Streamable HTTP | stdio or Streamable HTTP |
| **Client** | HTTP and MCP clients | MCP-compatible clients |
| **Run command** | `uvicorn src.api.main:app` | `uv run python -m src.mcp` |
