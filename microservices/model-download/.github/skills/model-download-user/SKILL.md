---
name: model-download-user
description: >
  Download and convert AI models using the Model Download microservice.
  Use this skill whenever a user wants to: download a model from HuggingFace,
  Ollama, Ultralytics, Geti, or Pipeline Zoo; convert a model to OpenVINO IR
  format for OVMS; download healthcare AI models (3D Pose, rPPG, AI-ECG) via
  the HLS plugin; set up the model download service; submit a download or
  conversion job via the REST API or the MCP server; connect an MCP client
  (Claude Desktop, Copilot) to model-download; or ask "how do I get model X
  working with OVMS?". Also trigger on phrases like "download model",
  "download weights", "convert to int4", "OVMS-ready model", "prepare model
  for inference", "model-download MCP server".
metadata:
  argument-hint: >
    Describe the model you want (e.g. "download Llama-3.2-1B from HuggingFace
    and convert to OpenVINO INT4 for CPU with OVMS")
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Model Download Agent

Set up the Model Download microservice and walk the user through downloading
or converting any supported model using the REST API or the MCP server.

> **Preview:** This skill is in preview — share feedback to help improve it.

## When to Use

- User wants to download a model from HuggingFace, Ollama, Ultralytics, Geti, Pipeline Zoo, or HLS
- User wants to convert a HuggingFace model to OpenVINO IR format for OVMS deployment
- User asks about model precision conversion (INT4/INT8/FP16/FP32)
- User needs to target a specific device (CPU, GPU, NPU, or HETERO combinations like `HETERO:GPU,CPU`)
- User wants to download healthcare AI models (3D Pose, rPPG, AI-ECG)
- User is integrating model downloads into a Docker Compose workflow

## MCP Server (Alternative to REST)

Every Model Download deployment also exposes an **MCP server** at `/mcp`
alongside the REST API, so agents like Claude Desktop, GitHub Copilot, and
custom MCP clients can call the service directly as tools instead of issuing
raw `curl` requests.

- Same service, same port (`8200`) — no separate process required for the
  container deployment; `uv run python -m src.mcp` runs it standalone (stdio)
  for local/agent-only use.
- Tools mirror the REST surface: `health_check`, `download_model`,
  `get_job_status`, `list_jobs`, `cancel_job`, `get_model_jobs`,
  `get_model_results`, `list_plugins`, `list_hub_models`.
- Resources: `models://jobs`, `models://jobs/{job_id}`, `models://results`,
  `models://plugins`.
- **If the user's request comes through an MCP client (Claude Desktop,
  Copilot with the `model-download` MCP server connected, etc.), prefer
  calling the matching MCP tool directly** instead of constructing a `curl`
  command — the tool signatures accept the same fields (`name`, `hub`,
  `type`, `is_ovms`, `config`, `revision`, `download_path`), and `download_model`
  additionally accepts top-level `override_credentials` (a dict such as
  `{"HF_TOKEN": "<base64-encoded-token>"}`) and `validate_credentials`
  (bool) — the same per-request, base64-encoded auth override available
  on the REST endpoint. `list_hub_models` also accepts `override_credentials`
  for listing models on a gated/private hub.
- Full client setup (Claude Desktop / Copilot config, HTTP client example,
  verification steps) lives in
  `docs/user-guide/get-started/using-mcp-server.md` — read it when the user
  asks to configure or troubleshoot an MCP client.

> Note: this skill's "Supported Hubs at a Glance" table and the
> `example-prompts/` files are also served live as MCP prompts by
> `src/mcp/prompts.py`. Keep the heading text and file names stable when
> editing them.

## Supported Hubs at a Glance

| Hub | `hub` value | What it does | Required env vars |
|-----|-------------|--------------|-------------------|
| HuggingFace | `huggingface` | Downloads any public or gated HF model | `HUGGINGFACEHUB_API_TOKEN` for compose-based startup (gated only) |
| Ollama | `ollama` | Downloads Ollama models, runs local Ollama server | — |
| Ultralytics | `ultralytics` | Downloads YOLO models, optional INT8 quantization | — |
| OpenVINO | `openvino` | Converts HF models to OpenVINO IR for OVMS | `HUGGINGFACEHUB_API_TOKEN` for compose-based startup (usually needed) |
| Geti | `geti` | Downloads trained models from Intel Geti platform | `GETI_HOST`, `GETI_TOKEN`, `GETI_WORKSPACE_ID` |
| Pipeline Zoo | `pipeline-zoo-models` | Downloads DL Streamer pipeline-zoo models | — |
| HLS | `hls` | Downloads healthcare AI models (3d-pose, rppg, ai-ecg) | — |
| Open Model Zoo | `omz` | Downloads + converts OMZ models via `omz_downloader`/`omz_converter` | — |
| Remote URL | `remote-url` | Downloads a tarball archive from a `config.url`, checked against an allowlist | — |

## Gated HuggingFace Models — Token Handling

Applies to **both** `hub: "huggingface"` and `hub: "openvino"` (the OpenVINO
converter downloads the source weights from HuggingFace before converting, so
gated-model auth works identically for conversion requests).

There are **two distinct ways** to supply an HF token, and they use **different
encodings** — mixing them up is the most common gated-model failure:

| Path | Where the token goes | Encoding |
|------|----------------------|----------|
| Compose/service startup (`run_service.sh up`) or `get_model.sh` CLI | `HUGGINGFACEHUB_API_TOKEN` / `HF_TOKEN` environment variable on the host | **Plain text** (`hf_...`), never base64 |
| Per-request override via REST/MCP `download_model` call | top-level `override_credentials.HF_TOKEN` field on the model entry — a **sibling of `name`/`hub`/`config`**, not nested inside `config` | **Base64-encoded**, always — required even though the field also supports a `sensitive` flag |

Encode a token before putting it in `override_credentials`:
```bash
echo -n 'hf_xxx' | base64
```

**If the user's request arrives through the MCP client and the model is gated**,
prefer `override_credentials` with a base64-encoded `HF_TOKEN` over asking them to
restart the whole service with a new environment variable — it avoids a container
restart. For `is_ovms` conversion requests, also set `validate_credentials: true`
so a bad/wrongly-encoded token is caught before the (often multi-minute)
conversion runs, instead of failing only after it completes.

**CLI failure scenario:** If a base64-encoded token is exported for
`get_model.sh` (or passed as `HUGGINGFACEHUB_API_TOKEN`/`HF_TOKEN` to
`run_service.sh up`), authentication fails with `401 Unauthorized` /
`Repository ... is gated` even though the token looks "set" — the CLI and
compose startup path send the value through unmodified, so a base64 string is
not a valid HF token. This applies to `--hub huggingface` and `--hub openvino`
CLI invocations alike. See
[troubleshooting.md](./references/troubleshooting.md#huggingface-authentication-errors)
for the fix.

## Ollama Quick-Reference

> **Always use these exact field names for Ollama requests — the API differs from what
> generic model-download documentation implies.**

```json
{
  "models": [
    {
      "hub": "ollama",
      "name": "<model-family>",
      "revision": "<tag>"
    }
  ]
}
```

- **`hub`** must be `"ollama"` (not `model_hub`, not `type`)
- **`name`** is the base model family: `"llama3.2"`, `"mistral"`, `"gemma2"` (no tag suffix)
- **`revision`** is the tag: `"3b"`, `"7b"`, `"latest"` (separate field, not `model_name`)
- **Port is always `8200`** (not 8080, not 8000)
- **Plugin flag**: `source scripts/run_service.sh up --plugins ollama`

Example — download llama3.2:3b:
```bash
curl -s -X POST "http://localhost:8200/api/v1/models/download?download_path=ollama-models" \
  -H "Content-Type: application/json" \
  -d '{"models": [{"hub": "ollama", "name": "llama3.2", "revision": "3b"}]}'
```

## Common Mistakes to Avoid

| Mistake | Correct |
|---------|---------|
| Port `8080` or `8000` | Port **`8200`** always |
| `"model_hub": "ollama"` | `"hub": "ollama"` |
| `"model_name": "llama3.2:3b"` | `"name": "llama3.2", "revision": "3b"` |
| `docker compose up -d` | `source scripts/run_service.sh up --plugins <list>` |
| Starting without `--plugins <hub>` | Always activate the plugin for your hub |
| Polling `/api/v1/jobs` without job ID | Use the `job_ids[0]` from the download response |

---

## Reference Lookup

Read a reference file only when you need the detail it contains:

| Reference | When to read |
|-----------|-------------|
| [service-setup.md](./references/service-setup.md) | Starting the service, Docker Compose, plugin flags, env vars |
| [plugins-guide.md](./references/plugins-guide.md) | Per-plugin request bodies, parameters, and curl examples |
| [troubleshooting.md](./references/troubleshooting.md) | Auth errors, stuck jobs, plugin not activated, venv failures |

---

## Procedure

### Execution Overview

After Step 0 (gather requirements), start the service setup in parallel with composing the API call.

```
Step 0 (gather requirements — interactive)
  │
  ├──► Step 1 (service setup — may require user action)
  └──► Step 2 (compose API call body — reasoning)
         │
         ├──► Step 3 (submit job + poll status)
         └──► Step 4 (verify result + next steps)
```

---

### Step 0 — Gather Requirements

Extract the following from the user's prompt. If anything is missing, ask before proceeding.

| Required | What to look for | Default if absent |
|----------|-----------------|-------------------|
| **Model name** | Exact model identifier (e.g. `meta-llama/Llama-3.2-1B`) | Must ask |
| **Hub** | One of: `huggingface`, `openvino`, `ollama`, `ultralytics`, `geti`, `pipeline-zoo-models`, `hls`, `omz`, `remote-url` | Must ask |
| **Conversion needed?** | User says "OVMS", "OpenVINO format", "convert", "is_ovms" | `false` |
| **Device** | CPU / GPU / NPU / `HETERO:<dev>[,<dev>...]` (e.g. `HETERO:GPU,CPU`) | `CPU` |
| **Precision** | int4 / int8 / fp16 / fp32 | `int8` for LLMs; `fp16` for others |
| **Model type** | llm / vlm / embeddings / rerank / text2speech / speech2text / image_generation / vision / 3d-pose / rppg / ai-ecg | Infer from context |

**OpenVINO-specific rules (ask only if the user wants OVMS / OpenVINO conversion):**
- NPU forces `int4` regardless of other settings (applies only to the exact `NPU` device, not HETERO combinations such as `HETERO:NPU,CPU`)
- HETERO devices appear in the output path as a filesystem-safe slug: `HETERO:GPU,CPU` → `openvino_models/hetero_gpu_cpu/`
- LLM/VLM conversions support `cache_size` (KV cache in GB) — ask if user mentioned memory constraints
- Embeddings and reranker conversions use `text_generation`/`embeddings_ov`/`rerank_ov` export types internally — these are resolved automatically from `type`

**If the user's prompt explicitly names a model AND hub**, go straight to Step 1. Otherwise ask.

---

### Step 1 — Service Setup

Read [service-setup.md](./references/service-setup.md) for full details.

Show the user the service startup command, using only the plugins their request requires:

```bash
# Clone (if not already done)
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
cd edge-ai-libraries/microservices/model-download

# Set env vars
export HUGGINGFACEHUB_API_TOKEN=<your-hf-token>   # mapped into the container as HF_TOKEN
export REGISTRY="intel/"
export TAG=latest

# Start service (adjust --plugins to match what you need)
source scripts/run_service.sh up --plugins <comma-separated-list> --model-path $PWD/models
```

Plugin list recommendations:
- HuggingFace only → `--plugins huggingface`
- HuggingFace + OpenVINO conversion → `--plugins huggingface,openvino`
- Ollama → `--plugins ollama`
- Ultralytics → `--plugins ultralytics`
- All → `--plugins all`

Confirm the service is healthy before proceeding:
```bash
curl http://localhost:8200/api/v1/health
# Expected: {"status": "ok"}
```

---

**Every final answer to the user must restate both the exact startup command (with the
right `--plugins` list) and the port `8200`** — not just the request payload. Users copy
answers piecemeal, so a payload without its startup command or port is easy to misapply.

### Step 2 — Compose the API Request

Read [plugins-guide.md](./references/plugins-guide.md) for the exact request body for each plugin.

The general request shape for `POST /api/v1/models/download?download_path=<subdir>` is:

```json
{
  "models": [
    {
      "name": "<model-identifier>",
      "hub": "<hub-value>",
      "type": "<model-type-or-omit>",
      "is_ovms": false,
      "config": {},
      "override_credentials": {},
      "validate_credentials": false
    }
  ],
  "parallel_downloads": false
}
```

Key rules:
- `is_ovms: true` triggers OpenVINO conversion
- Use `hub: "openvino"` with `is_ovms: true` and a `type` field for conversion
- `config` holds precision, device, cache_size, `post_processing` (OMZ), and other plugin-specific params
- `override_credentials` (base64-encoded) and `validate_credentials` are top-level fields on each model entry — see "Gated HuggingFace Models" above
- `parallel_downloads` (top-level, sibling of `models`) opts multiple entries in one request into concurrent downloads; omit/`false` processes them sequentially (Ollama always serializes regardless)
- `download_path` query param sets the subdirectory under the model store — the final output path is `<model-path>/<download_path>/<hub-specific-subpath>`

---

### Step 3 — Submit Job and Poll Status

```bash
# 1. Submit download job
JOB_RESPONSE=$(curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=my-models" \
  -H "Content-Type: application/json" \
  -d '<your-request-body>')

echo "$JOB_RESPONSE"
# Response: {"message": "Started processing 1 model(s)", "job_ids": ["<uuid>"], "status": "processing"}

# 2. Extract job ID
JOB_ID=$(echo "$JOB_RESPONSE" | jq -r '.job_ids[0]')

# 3. Poll until completed or failed
watch -n 5 "curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | jq ."
```

Job status values: `queued` → `downloading` / `converting` → `completed` / `failed`

If status is `failed`, read the `error` field and check [troubleshooting.md](./references/troubleshooting.md).

---

### Step 4 — Verify and Next Steps

```bash
# List all completed downloads
curl -s http://localhost:8200/api/v1/models/results | jq .

# Check a specific model's jobs
curl -s "http://localhost:8200/api/v1/models/jobs?model_name=<model-name>" | jq .
```

After confirming success, tell the user:
- The host path where the model was saved (shown in the job result's `download_path`)
- For OVMS conversions: how to mount the model directory into OVMS and which model name to use; the result uses `conversion_path`
- For Ollama: the model is stored inside the container's model store volume

**Important accuracy note for OpenVINO conversions:** Use `hub: "openvino"` with `is_ovms: true`
for model conversion.

**Quick alternative:** For one-shot, ephemeral container use (CI/CD, scripted workflows), use the `get_model.sh` one-liner
```bash
curl -sSLO https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/model-download/scripts/get_model.sh
source ./get_model.sh --model-name <model> --hub <hub> --plugins <plugins>
```
