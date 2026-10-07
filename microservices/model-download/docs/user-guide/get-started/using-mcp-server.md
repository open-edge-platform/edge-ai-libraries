<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Model Download MCP Server

Every Model Download deployment exposes an **MCP (Model Context Protocol) server** at `/mcp` alongside the REST API. LLM agents (Claude Desktop, GitHub Copilot, and custom AI agents) can therefore download, convert, and manage AI models through MCP without deploying a second service.

## Quick Start

### Recommended: Container MCP Endpoint

Deploy the Model Download service first, then configure MCP clients to connect
to the HTTP MCP endpoint exposed by that deployment. This is required for
OpenVINO/OVMS conversions because the container entrypoint:

- downloads the OVMS `export_model.py` script;
- creates the dedicated OpenVINO plugin virtual environment;
- installs the matching conversion dependencies; and
- records the plugin environment in `/opt/plugin_venvs.env`.

Start the service with the plugins required for Hugging Face downloads and
OpenVINO conversion:

```bash
cd edge-ai-libraries/microservices/model-download

# Required only for gated/private Hugging Face models. The environment-variable
# path expects the plain-text token, not a base64-encoded value.
export HUGGINGFACEHUB_API_TOKEN='hf_xxx'

source scripts/run_service.sh up \
  --plugins huggingface,openvino \
  --model-path "$PWD/models"
```

Verify the service before configuring the MCP client:

```bash
curl http://localhost:8200/api/v1/health
# Expected: {"status":"ok"}
```

Connect MCP clients to:

```text
http://localhost:8200/mcp
```

The deployment serves both interfaces on port `8200`:

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

### GitHub Copilot

First deploy the service as described in
[Recommended: Container MCP Endpoint](#recommended-container-mcp-endpoint).
Then remove any existing local/stdio configuration and connect Copilot directly
to the same HTTP MCP endpoint used by the REST service and MCP Inspector:

```bash

copilot mcp add \
  --transport http \
  --tools '*' \
  oep-model-download \
  http://localhost:8200/mcp
```

If the MCP endpoint is on another host, replace `localhost` with the hostname
used by MCP Inspector. After adding or changing the server, restart Copilot CLI
or reload the server through `/mcp`.

This configuration ensures REST, MCP Inspector, and Copilot share the same
container-initialized plugin environment, model store, and job manager.

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

For an HTTP configuration, verify the container endpoint and the Copilot
configuration:

```bash
curl http://localhost:8200/api/v1/health
copilot mcp get oep-model-download
```

For a standalone stdio configuration, run the configured
`uv run --directory ...` command in a terminal to expose startup errors. If
health succeeds but a model operation fails, use `list_plugins` to check plugin
activation and availability, then inspect the error returned by
`get_job_status`.

For OpenVINO conversion failures that occur only in Copilot CLI:

1. Check whether `copilot mcp get oep-model-download` reports `Type: local`.
2. If it does, the CLI is launching a separate standalone stdio server rather
   than using the container runtime.
3. Replace that configuration with the HTTP configuration shown in
   [GitHub Copilot](#github-copilot).
4. Do not start an additional `uv run python -m src.mcp` process.

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
| `HUGGINGFACEHUB_API_TOKEN` / `HF_TOKEN` | Plain-text Hugging Face API token for gated/private models | — |
| `ENABLED_PLUGINS` | Comma-separated list of plugins to activate | `all` |

## REST API vs MCP Server

Both modes share the same core logic (`ModelManager`, `PluginRegistry`). Choose based on your use case:

| | Default deployment | Standalone MCP |
|---|---|---|
| **Use when** | Applications need REST/MCP, or any OpenVINO/OVMS conversion | Download-only local development |
| **Transport** | REST and Streamable HTTP | stdio or Streamable HTTP |
| **Client** | HTTP and MCP clients | MCP-compatible clients |
| **Run command** | `uvicorn src.api.main:app` | `uv run python -m src.mcp` |
| **OpenVINO bootstrap** | Performed by the container entrypoint | Not performed automatically |
