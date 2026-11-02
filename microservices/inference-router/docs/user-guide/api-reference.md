# API Reference

The router exposes an OpenAI-compatible API. All examples assume the router is
running on `localhost:8000`.

## Service Info

Endpoint:

```bash
GET /
```

**Example:**

```bash
curl http://localhost:8000/
```

**Description:**

Returns service name, version, status, and a map of available endpoints.

**Response:**

- 200 OK:

  ```json
  {
      "name": "Inference Router API",
      "version": "0.1.0",
      "status": "running",
      "endpoints": {
          "health": "/health",
          "chat": "/v1/chat/completions",
          "models": "/v1/models",
          "metrics": "/v1/metrics",
          "config": "/v1/config",
          "routing": "/v1/routing",
          "providers": "/v1/providers",
          "policies": "/v1/policies",
          "strategies": "/v1/strategies",
          "audio_transcriptions": "/v1/audio/transcriptions",
          "audio_speech": "/v1/audio/speech",
          "embeddings": "/v1/embeddings",
          "rerank": "/v1/rerank",
          "ocr": "/v1/ocr"
      }
  }
  ```

## Health Check

Endpoint:

```bash
GET /health
```

**Example:**

```bash
curl http://localhost:8000/health
```

**Description:**

Verifies that the router is alive and operational. Includes router
initialization status and current concurrency counters.

**Response:**

- 200 OK:

  ```json
  {
      "status": "healthy",
      "router": "initialized",
      "timestamp": 1733040000,
      "concurrency": {
          "active_requests": 0,
          "max_concurrency": 3
      }
  }
  ```

  `max_concurrency` is the integer limit, or the string `"unlimited"` when no
  limit is set.

- 503 Service Unavailable:

  ```json
  {"detail": "Router not initialized"}
  ```

## List Models

Endpoint:

```bash
GET /v1/models
```

**Example:**

```bash
curl http://localhost:8000/v1/models
```

**Description:**

Lists every available model. One entry per enabled provider in `config.yaml`,
where `id` is the configured backend model name (the value clients pass in
`request.model` to route here) and `owned_by` is the provider name. Two
providers MAY share an `id` — they're distinguishable by `owned_by`, and
routing by model name picks the first such provider in configuration order; pass
the provider name in `request.model` to target the other. The response
always includes the virtual model `"auto"` for automatic routing.

Pass-through providers (`type` of `transcription`, `tts`, `embeddings`,
`rerank`, or `ocr`) are **not** chat-capable models and are omitted from this
list; they are reachable via their dedicated endpoints (see
[Pass-through Services](#pass-through-services)) and manageable via
`/v1/providers`.

**Response:**

- 200 OK:

  ```json
  {
      "object": "list",
      "data": [
          {
              "id": "Qwen/Qwen3-8B",
              "object": "model",
              "created": 1733040000,
              "owned_by": "local"
          },
          {
              "id": "MiniMax-M2.7",
              "object": "model",
              "created": 1733040000,
              "owned_by": "cloud"
          },
          {
              "id": "auto",
              "object": "model",
              "created": 1733040000,
              "owned_by": "inference-router"
          }
      ]
  }
  ```

## Chat Completions

Endpoint:

```bash
POST /v1/chat/completions
```

**Example:**

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

**Description:**

OpenAI-compatible chat completion. Set `model` to a specific ID to pin the
backend, or to `"auto"` for smart routing. Set `stream: true` for
Server-Sent Events (SSE) streaming.

**Request Body:**

```json
{
    "model": "auto",
    "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"}
    ],
    "stream": false,
    "temperature": 0.7,
    "max_tokens": 200
}
```

- `model`: Either `"auto"` for smart routing, a model ID from `/v1/models`
  (the primary path), or a configured provider name (legacy fallback —
  useful when two providers share a model ID and you need to target a
  specific one).
- `messages`: List of OpenAI-format messages.
- `stream`: When `true`, response is streamed as SSE.
- Other OpenAI parameters, such as `temperature`, `max_tokens`, `top_p`,
  `tools`, `tool_choice`, and `response_format`, pass through to the backend.

**Response (non-streaming):**

- 200 OK:

  ```json
  {
      "id": "chatcmpl-...",
      "object": "chat.completion",
      "created": 1733040000,
      "model": "Qwen/Qwen3-8B",
      "choices": [
          {
              "index": 0,
              "message": {"role": "assistant", "content": "..."},
              "finish_reason": "stop"
          }
      ],
      "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
  }
  ```

**Response (streaming):**

- 200 OK with `Content-Type: text/event-stream`. Each chunk is an SSE
  `data: {...}` line. The stream ends with `data: [DONE]`.

**Errors:**

- 400 Bad Request: routing failed (e.g. unknown model name).
- 4xx (forwarded): upstream client errors from the backend provider (e.g. an
  invalid payload) are forwarded verbatim with the provider's own status code.
- 422 Unprocessable Entity: request validation failed.
- 429 Too Many Requests: concurrency limit reached.
- 500 Internal Server Error: inference or unexpected failure.
- 502 Bad Gateway: upstream provider error (non-4xx).
- 503 Service Unavailable: router not initialized.

## Pass-through Services

The router can expose additional OpenAI- and Cohere-compatible endpoints that
**forward the request body verbatim** to a backing service and return the
response untouched. Each is enabled by adding a **provider** whose `type` names
the service (see [Create or Update Provider](#create-or-update-provider) and the
[Get Started](./get-started.md#optional-pass-through-services)) sections. If
there is no such provider configured for a service, that endpoint returns `503`.

| Provider `type` | Endpoint                        | Body / Response                       |
| --------------- | ------------------------------- | ------------------------------------- |
| `transcription` | `POST /v1/audio/transcriptions` | multipart or JSON in, JSON out        |
| `tts`           | `POST /v1/audio/speech`         | JSON in, binary audio out             |
| `embeddings`    | `POST /v1/embeddings`           | JSON in, JSON out                     |
| `rerank`        | `POST /v1/rerank`               | JSON in, JSON out (Cohere-compatible) |
| `ocr`           | `POST /v1/ocr`                  | multipart or JSON in, JSON out        |

**Behavior (all pass-through endpoints):**

- The request body and `Content-Type` (including a multipart boundary) are
  forwarded unchanged; the client's headers are passed through with `Host`
  stripped. Configured `settings.auth` on the provider is applied to the
  upstream call.
- The upstream response status, body, and headers are returned as-is
  (hop-by-hop headers are regenerated).
- Requests count against `max-concurrency`, shared with `/v1/chat/completions`.
- These endpoints are managed dynamically through `/v1/providers`; enabling,
  disabling, or deleting the provider takes effect immediately.

**Examples:**

Transcribe audio:

```bash
curl http://localhost:8000/v1/audio/transcriptions \
  -F "file=@audio.wav" \
  -F "model=whisper-1"
```

Generate speech:

```bash
curl http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model": "tts-1", "voice": "alloy", "input": "Hello world"}' \
  -o speech.mp3
```

Create embeddings:

```bash
curl http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "bge-m3", "input": "hello world"}'
```

Rerank documents:

```bash
curl http://localhost:8000/v1/rerank \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rerank-english-v3.0",
    "query": "What is the router?",
    "documents": ["A routing service", "A storage service"]
  }'
```

Run OCR:

```bash
curl http://localhost:8000/v1/ocr \
  -H "Content-Type: application/json" \
  -d '{"image_path": "/data/page.png"}'
```

**Errors:**

- 429 Too Many Requests: concurrency limit reached.
- 502 Bad Gateway: could not reach the backing service.
- 503 Service Unavailable: no provider configured for this service, or router
  not initialized.
- 504 Gateway Timeout: the backing service did not respond within
  `settings.timeout`.

## Metrics

Endpoint:

```bash
GET /v1/metrics
```

**Example:**

```bash
curl http://localhost:8000/v1/metrics
```

**Description:**

Aggregated routing, token, and latency metrics, bucketed by provider name.
Counters accumulate from process start (or the last `POST /v1/metrics/reset`)
across both streaming and non-streaming requests.

**Response:**

- 200 OK: object with three top-level sections:

  The `by_provider` map keys are `"<provider>/<model>"`, where each key is the
  configured provider name followed by the backend model ID; for example,
  `"local/Qwen/Qwen3.5-9B"`. When one provider serves multiple models, or two
  providers expose the same model, each (provider, model) pair gets its own
  bucket so dashboards can disambiguate them. The field name remains
  `by_provider` for back-compat with pre-existing dashboards; only the key
  strings changed.

  - `routing_stats` — total request count and per-bucket request counts.
  - `token_metrics` — per-bucket input, output, and total token counts plus
    `request_share` and `token_share` (fractions of the overall traffic), and
    an `overall` aggregate. Also carries two request-level token breakdowns:
    `before_router` (the raw request) and `after_router` (the request actually
    forwarded to the backend after router plugins run). Both use the same
    tiktoken unit, so the delta between them is the token saving from
    router-side processing (e.g. context compression). Each breakdown reports
    `system_prompt_tokens`, `tool_schema_tokens`, `context_tokens`, and
    `overall_tokens`.
  - `latency_metrics` — per-bucket average end-to-end latency, TTFT
    (time-to-first-token), and TPOT (time-per-output-token), plus an `overall`
    aggregate. TTFT is reported only for streaming requests; non-streaming
    requests contribute to `avg_latency_ms` only.

  Example:

  ```json
  {
      "routing_stats": {
          "total_requests": 12,
          "by_provider": {
              "local/Qwen/Qwen3.5-9B": 8,
              "cloud/MiniMax-M2.7": 4
          }
      },
      "token_metrics": {
          "by_provider": {
              "local/Qwen/Qwen3.5-9B": {
                  "input_tokens": 1200,
                  "output_tokens": 800,
                  "total_tokens": 2000,
                  "request_count": 8,
                  "avg_tokens_per_request": 250.0,
                  "request_share": 0.667,
                  "token_share": 0.625
              }
          },
          "overall": {
              "total_tokens": 3200,
              "total_input_tokens": 1900,
              "total_output_tokens": 1300,
              "total_requests": 12,
              "avg_tokens_per_request": 266.7
          },
          "before_router": {
              "system_prompt_tokens": 300,
              "tool_schema_tokens": 150,
              "context_tokens": 1450,
              "overall_tokens": 1900
          },
          "after_router": {
              "system_prompt_tokens": 300,
              "tool_schema_tokens": 150,
              "context_tokens": 1100,
              "overall_tokens": 1550
          }
      },
      "latency_metrics": {
          "by_provider": {
              "local/Qwen/Qwen3.5-9B": {
                  "avg_latency_ms": 420.15,
                  "avg_ttft_ms": 35.20,
                  "avg_tpot_ms": 4.8123,
                  "ttft_count": 5,
                  "tpot_count": 5
              }
          },
          "overall": {
              "avg_latency_ms": 510.40,
              "avg_ttft_ms": 38.10,
              "avg_tpot_ms": 5.1042,
              "ttft_count": 7,
              "tpot_count": 7
          }
      }
  }
  ```

- 503 Service Unavailable:

  ```json
  {"detail": "Telemetry not initialized"}
  ```

## Reset Metrics

Endpoint:

```bash
POST /v1/metrics/reset
```

**Example:**

```bash
curl -X POST http://localhost:8000/v1/metrics/reset
```

**Description:**

Clears all telemetry metrics.

**Response:**

- 200 OK:

  ```json
  {
      "status": "success",
      "message": "All statistics metrics have been reset",
      "timestamp": 1733040000
  }
  ```

## Get Configuration

Endpoint:

```bash
GET /v1/config
```

**Example:**

```bash
curl http://localhost:8000/v1/config
```

**Description:**

Returns the current in-memory router configuration. Sensitive values (keys
named `api_key`, `token`, `secret`, or `password`) are replaced with
`"***REDACTED***"` in the response.

**Response:**

- 200 OK:

  ```json
  {
      "object": "config",
      "data": {
          "log_level": "INFO",
          "providers": [
              {
                  "name": "local",
                  "type": "openai",
                  "model": "Qwen/Qwen3-8B",
                  "enabled": true,
                  "metadata": {},
                  "settings": {"api_key": "***REDACTED***"}
              }
          ],
          "plugins": {
              "prerouting": [],
              "postrouting": [],
              "postresponse": []
          },
          "routing": {"policy": "default", "strategy": "auto"},
          "telemetry": {
              "backend": "memory",
              "enabled": true,
              "file_path": null
          },
          "cors_origins": ["*"]
      },
      "path": "/path/to/config.yaml",
      "warnings": []
  }
  ```

  `path` is the on-disk configuration file path (or `null` if not configured).
  `warnings` lists non-fatal advisories about the configuration.

- 503 Service Unavailable:

  ```json
  {"detail": "Router not initialized"}
  ```

## Get Routing

Endpoint:

```bash
GET /v1/routing
```

**Example:**

```bash
curl http://localhost:8000/v1/routing
```

**Description:**

Returns the active routing policy — the `policy` field of the configuration's `routing`
section. The policy names an entry in `policy.yaml` that decides how requests are
dispatched across providers.

**Response:**

- 200 OK:

  ```json
  {"policy": "Balanced"}
  ```

  `policy` is `null` if none is configured (the router then falls back to the
  first policy defined in `policy.yaml`).

- 503 Service Unavailable:

  ```json
  {"detail": "Router not initialized"}
  ```

## Update Routing

Endpoint:

```bash
POST /v1/routing
```

**Example:**

```bash
curl http://localhost:8000/v1/routing \
  -H "Content-Type: application/json" \
  -d '{"policy": "Balanced"}'
```

**Description:**

Sets the routing policy, then persists the change to the on-disk configuration and
rebuilds the runtime. The policy must name an entry in `policy.yaml`; an unknown
name is rejected and the previous policy stays in effect. Provider secrets in
`config.yaml` (e.g. `${VAR}` placeholders) are left untouched.

The new policy's `ModelBasedRule` classifiers are loaded before the switch.
A classifier version that cannot be loaded degrades — the rule falls back to
the packaged default, or to `-1` (no classifier guidance) if even that is
unavailable; requests keep being served. `GET /v1/strategies/{name}` reports
the resulting `status`.

**Request Body:**

```json
{"policy": "Balanced"}
```

- `policy`: the routing policy name (must exist in `policy.yaml`).

**Response:**

- 200 OK: the resulting routing policy.

  ```json
  {"policy": "Balanced"}
  ```

- 400 Bad Request: the rebuilt runtime failed to initialize — e.g. the policy
  name is not found in `policy.yaml`.
- 500 Internal Server Error: failed to persist the configuration.
- 503 Service Unavailable: router not initialized.

## List Providers

Endpoint:

```bash
GET /v1/providers
```

**Example:**

```bash
curl http://localhost:8000/v1/providers
```

**Description:**

Lists all configured providers. Sensitive values (keys named `api_key`,
`token`, `secret`, or `password`) are replaced with `"***REDACTED***"` in the
response.

**Response:**

- 200 OK:

  ```json
  {
      "object": "list",
      "data": [
          {
              "name": "local",
              "type": "hosted_vllm",
              "model": "Qwen/Qwen3.5-9B",
              "enabled": true,
              "metadata": {
                  "labels": ["planning", "local"],
                  "cost": 0,
                  "performance": 0.85,
                  "capability": {"complexity": 0.75}
              },
              "settings": {
                  "endpoint": "http://localhost:5000/v1",
                  "timeout": 300.0,
                  "auth": {"scheme": "none", "api_key": null, "custom_headers": {}}
              }
          }
      ]
  }
  ```

- 503 Service Unavailable: router not initialized.

## Get Provider

Endpoint:

```bash
GET /v1/providers/{name}
```

**Example:**

```bash
curl http://localhost:8000/v1/providers/local
```

**Description:**

Returns a single provider's configuration, identified by its unique `name`.
Secrets are redacted as in `GET /v1/providers`.

**Response:**

- 200 OK: a single `ProviderResponse` (same structure as an entry in the list above).
- 404 Not Found: no provider with that `name`.

  ```json
  {"detail": "Provider 'local' not found"}
  ```

## Create or Update Provider

Endpoint:

```bash
POST /v1/providers/{name}
```

**Example:**

```bash
curl http://localhost:8000/v1/providers/openai \
  -H "Content-Type: application/json" \
  -d '{
    "type": "openai",
    "model": "gpt-4o",
    "enabled": true,
    "settings": {
      "endpoint": "https://api.openai.com/v1",
      "auth": {"scheme": "bearer", "api_key": "${OPENAI_API_KEY}"}
    }
  }'
```

**Description:**

Creates or updates a provider, then persists the change to the on-disk configuration
and rebuilds the runtime. The provider is created if it does not exist, and
updated otherwise. Only the fields present in the request body are changed;
`settings` and `metadata`, when supplied, replace the existing section wholesale.

Secrets are preserved on disk: an `api_key` written as an environment
placeholder (e.g. `"${OPENAI_API_KEY}"`) is stored verbatim in `config.yaml`
rather than being resolved to its value. Providers that are left untouched keep
their existing placeholders unchanged.

**Request Body:**

```json
{
    "type": "openai",
    "model": "gpt-4o",
    "enabled": true,
    "metadata": {"labels": ["cloud"], "cost": 5},
    "settings": {
        "endpoint": "https://api.openai.com/v1",
        "auth": {"scheme": "bearer", "api_key": "${OPENAI_API_KEY}"}
    }
}
```

- `type`: provider type (e.g. `hosted_vllm`, `openai`). **Required when creating**
  a new provider; optional on update.
- `model`: backend model identifier. **Required when creating**; optional on update.
- `enabled`: optional. Toggle the provider on or off.
- `metadata`: optional. Routing metadata (labels, cost, performance, capability;
  extra fields allowed).
- `settings`: optional. Provider-specific settings such as `endpoint`, `timeout`,
  and `auth` (extra fields allowed).

**Response:**

- 200 OK: the resulting `ProviderResponse` (secrets redacted).
- 400 Bad Request: creating a new provider without both `type` and `model`, or the
  rebuilt runtime failed to initialize (e.g. no enabled providers remain).
- 500 Internal Server Error: failed to persist the configuration.
- 503 Service Unavailable: router not initialized.

## Delete Provider

Endpoint:

```bash
DELETE /v1/providers/{name}
```

**Example:**

```bash
curl -X DELETE http://localhost:8000/v1/providers/openai
```

**Description:**

Removes a provider, persists the change to the on-disk configuration, and rebuilds the
runtime.

This edits configuration only. To stop a backend started via the
`provider_management` plugin, also call its lifecycle endpoint
`DELETE /v1/providers/manage?name=<name>` (see
[Stop Provider](#stop-provider-lifecycle)), which tells the Local Provider
Manager to tear the container down.

**Response:**

- 200 OK:

  ```json
  {"status": "success", "message": "Provider 'openai' deleted"}
  ```

- 400 Bad Request: the rebuilt runtime failed to initialize (e.g. deleting the
  last enabled provider). The change is rejected atomically — the configuration file is
  left unchanged.
- 404 Not Found: no provider with that `name`.
- 500 Internal Server Error: failed to delete the provider.
- 503 Service Unavailable: router not initialized.

## Start Provider (Lifecycle)

Endpoint:

```bash
POST /v1/providers/manage
```

**Example:**

```bash
curl http://localhost:8000/v1/providers/manage \
  -H "Content-Type: application/json" \
  -d '{
    "name": "qwen3-local",
    "image": "intel/llm-scaler-vllm:0.26.0-b2",
    "entrypoint": "vllm",
    "volumes": {"/path/to/Qwen3-8B": "/llm/models/Qwen3-8B"},
    "docker_args": ["--device", "/dev/dri", "-p", "24680:24680"],
    "command": ["serve", "/llm/models/Qwen3-8B", "--served-model-name", "qwen3",
                "--port", "24680", "--host", "0.0.0.0"],
    "health_endpoint": "http://localhost:24680/health"
  }'
```

**Description:**

Starts a serving backend (provider service) through an external **Local Provider
Manager**. Provided by the `provider_management` plugin (see
[Plugins](./plugin.md#provider_management-plugin)); the manager's base URL is
configured on the plugin instance as `manager_url` (or passed per request).

The docker parameters are forwarded to the manager verbatim; it runs
`docker run -d` and records the result. With `health_endpoint` the router waits
for the backend to answer 2xx before responding. The router config is **not**
touched: to route to the service, add or enable its provider with
[Create or Update Provider](#create-or-update-provider)
(e.g. `POST /v1/providers/{name}` with `{"enabled": true}`).

**Request Body:**

- `name`: **required**. Service name (letters, digits, `.`, `-`, `_`); the
  manager keys the container on it (`ir-provider-<name>`). It need not match a
  provider in the router config, though using the same name keeps things clear.
- `image`, `entrypoint`, `env`, `volumes`, `docker_args`, `command`: docker
  parameters forwarded to the manager (see the Local Provider Manager's API).
- `health_endpoint`: optional. URL, reachable from the router, polled until it
  returns 2xx before the router responds (e.g.
  `http://localhost:24680/health` for vLLM, `/v2/health/ready` for OVMS).
- `manager_url`: optional. Overrides the plugin's configured manager base URL.
- `management_timeout`: optional. Timeout in seconds for the manager call and for
  the readiness wait (cold starts can take minutes).

  `health_endpoint`, `manager_url` and `management_timeout` are consumed by the
  router and stripped before the request is forwarded to the manager.

**Response:**

- 2xx: the manager's record is passed through with its status code:

  ```json
  {
      "name": "qwen3-local",
      "container_name": "ir-provider-qwen3-local",
      "docker_command": "docker run -d --name ir-provider-qwen3-local --entrypoint vllm …",
      "status": "started",
      "container_id": "…",
      "error": null,
      "created_at": "2026-10-14T08:00:00+00:00",
      "state": "running"
  }
  ```

- 400 Bad Request: missing or invalid `name`, or no manager URL configured.
  Nothing is launched.
- 502 Bad Gateway: the container stopped before `health_endpoint` became ready
  (it is removed; the body's `provider` holds the manager's record), or the
  provider manager was unreachable.
- 504 Gateway Timeout: `health_endpoint` did not become ready within
  `management_timeout` (the container is removed), or the manager did not respond
  in time.
- other non-2xx (passed through): the manager rejected the start (e.g. 500 when
  `docker run` fails, 409 when the name is already in use).

## Stop Provider (Lifecycle)

Endpoint:

```bash
DELETE /v1/providers/manage?name={name}
```

**Example:**

```bash
curl -X DELETE "http://localhost:8000/v1/providers/manage?name=qwen3-local"
```

**Description:**

Stops and removes a provider service through the Local Provider Manager:
forwards `DELETE {manager_url}/providers/{name}` (the manager base URL comes from
the plugin's `manager_url` setting) and returns the manager's response. The router
config is **not** touched — disable or delete the provider via
[Create or Update Provider](#create-or-update-provider) /
[Delete Provider](#delete-provider) so the router stops routing to it.

**Query Parameters:**

- `name`: **required**. The service to stop.

**Response:**

- 2xx: the manager's response is passed through with its status code.
- 400 Bad Request: invalid `name`, or no manager URL configured.
- other non-2xx (passed through): e.g. 404 when the manager has no such service.
- 502 Bad Gateway / 504 Gateway Timeout: the provider manager was unreachable or
  did not respond in time.

## List Managed Providers (Lifecycle)

Endpoint:

```bash
GET /v1/providers/manage
```

**Example:**

```bash
curl http://localhost:8000/v1/providers/manage                      # all
curl "http://localhost:8000/v1/providers/manage?name=qwen3-local"   # one
```

**Description:**

Read-only proxy of the Local Provider Manager's **live** view of started
backends. Forwards `GET {manager_url}/providers` (or
`GET {manager_url}/providers/{name}` with the `?name=` query) and returns the
manager's response verbatim. Provided by the `provider_management` plugin; the
manager base URL comes from the plugin's `manager_url` setting.

This differs from [List Providers](#list-providers) (`GET /v1/providers`), which
reports the router's own configuration: this endpoint reports what is actually
running at the manager (the recorded `docker run` command and result, plus the
live container state). It does not read or change router config.

**Query Parameters:**

- `name`: optional. Return the status of a single managed provider instead of the
  full list.

**Response:**

- 2xx: the manager's response, passed through with its status code — a list of
  manager records (or a single record when `name` is given).
- 400 Bad Request: no manager URL configured (no `provider_management` plugin
  with `manager_url`).
- 404 Not Found: the manager has no provider with that `name` (passed through).
- 502 Bad Gateway / 504 Gateway Timeout: the provider manager was unreachable or
  did not respond in time.

## Load / Unload LoRA Adapter (Lifecycle)

Endpoints:

```bash
POST /v1/providers/manage/load_lora_adapter
POST /v1/providers/manage/unload_lora_adapter
```

**Example:**

```bash
curl http://localhost:8000/v1/providers/manage/load_lora_adapter \
  -H "Content-Type: application/json" \
  -d '{"provider": "qwen3-local", "lora_name": "sql_adapter", "lora_path": "/path/to/sql-lora-adapter"}'

curl http://localhost:8000/v1/providers/manage/unload_lora_adapter \
  -H "Content-Type: application/json" \
  -d '{"provider": "qwen3-local", "lora_name": "sql_adapter"}'
```

**Description:**

Dynamically loads or unloads a LoRA adapter on a running vLLM provider. Provided
by the `provider_management` plugin, but these calls bypass the Local Provider
Manager: the plugin strips `provider` from the body and forwards the rest to
`{endpoint}/v1/load_lora_adapter` (resp. `unload_lora_adapter`) on the provider's
`settings.endpoint` (a trailing `/v1` is handled), applying the provider's
configured `settings.auth`. Router config is not changed.

The vLLM server must be started with `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True`
(e.g. `-e VLLM_ALLOW_RUNTIME_LORA_UPDATING=True` in the start request's
`docker_args`) and LoRA enabled (`--enable-lora`). vLLM warns this feature is
only for isolated, fully trusted environments.

**Request Body:**

- `provider`: **required**. Name of a registered `hosted_vllm` provider.
- `lora_name`: **required**. Adapter name (the `model` to request it by).
- `lora_path`: **required for load**. Adapter path as seen by the vLLM server.
- Any other fields are forwarded to vLLM unchanged.

**Response:**

- 2xx: `{"provider": ..., "lora_name": ..., "message": "<vLLM's success text>"}`.
- 4xx/5xx from vLLM: its error response, passed through with its status code.
- 400 Bad Request: missing field, or the provider is not a `hosted_vllm` provider.
- 404 Not Found: no provider with that name.
- 503 Service Unavailable: the provider has no `settings.endpoint`.
- 502 Bad Gateway / 504 Gateway Timeout: the vLLM backend was unreachable or did
  not respond in time.

## List Plugins

Endpoint:

```bash
GET /v1/plugins
```

**Example:**

```bash
curl http://localhost:8000/v1/plugins
```

**Description:**

Lists all configured plugins.

**Response:**

- 200 OK:

  ```json
  {
      "object": "list",
      "data": [
          {
              "name": "dummy",
              "node": "dummy_logger",
              "enabled": true,
              "trigger": "prerouting",
              "settings": {}
          }
      ]
  }
  ```

- 503 Service Unavailable: router not initialized.

> **Terminology:** a **`node`** is a plugin *type* (a registered plugin class,
> e.g. `dummy_logger`); a **`name`** is one configured *instance* of that type.
> Instance routes are ordered node-first: `/v1/plugins/{node}/{name}`.

## List Plugin Nodes

Endpoint:

```bash
GET /v1/plugins/nodes
```

**Example:**

```bash
curl http://localhost:8000/v1/plugins/nodes
```

**Description:**

Lists the plugin **types** (nodes) registered in code, independent of what is
configured. Each entry carries the type's metadata and its settings JSON schema,
so a client can discover what a node accepts before configuring an instance.

**Response:**

- 200 OK:

  ```json
  {
      "object": "list",
      "data": [
          {
              "node": "dummy_logger",
              "plugin_group": "",
              "description": "Prints which phase invoked it; ...",
              "settings_schema": {"type": "object", "properties": {"label": {"type": "string"}}}
          }
      ]
  }
  ```

## Get Plugin Node

Endpoint:

```bash
GET /v1/plugins/{node}
```

**Example:**

```bash
curl http://localhost:8000/v1/plugins/dummy_logger
```

**Description:**

Node-level view of a plugin **type**, as defined by that plugin class's
`describe_node()` hook. The default payload is the type metadata (as in
`GET /v1/plugins/nodes`); a plugin may override `describe_node()` to add
node-level aggregate info (e.g. metrics spanning all instances of the type).

**Response:**

- 200 OK: a plugin-defined object (default = the node's metadata).
- 404 Not Found: `{node}` is not a registered plugin type.

  ```json
  {"detail": "Plugin node 'dummy_logger' not registered"}
  ```

## Get Plugin

Endpoint:

```bash
GET /v1/plugins/{node}/{name}
```

**Example:**

```bash
curl http://localhost:8000/v1/plugins/dummy_logger/dummy
```

**Description:**

Instance-level view of a configured plugin, as defined by the plugin's
`describe()` hook. Prefers the **live** instance (so per-instance runtime info
such as metrics is folded in); falls back to the static configuration view for a
configured-but-disabled plugin that is not loaded.

**Response:**

- 200 OK (a live `dummy_logger` instance folds its metrics into `describe()`):

  ```json
  {
      "name": "dummy",
      "node": "dummy_logger",
      "trigger": "prerouting",
      "enabled": true,
      "settings": {"label": "demo"},
      "metrics": {"process_request": 12, "process_response": 0}
  }
  ```

- 404 Not Found: no plugin with that `node`/`name`.

  ```json
  {"detail": "Plugin 'dummy' with node 'dummy_logger' not found"}
  ```

## Create or Update Plugin

Endpoint:

```bash
POST /v1/plugins/{node}/{name}
```

**Example:**

```bash
curl http://localhost:8000/v1/plugins/dummy_logger/dummy \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "trigger": "prerouting",
    "settings": {"label": "demo"}
  }'
```

**Description:**

Creates or updates a plugin instance, then persists the change to the on-disk
configuration and rebuilds the runtime. The instance is created if it does not exist,
and updated otherwise. Only the fields present in the request body are changed.

**Request Body:**

```json
{
    "enabled": true,
    "trigger": "prerouting",
    "settings": {"label": "demo"}
}
```

- `enabled`: optional. Toggle the plugin on or off.
- `trigger`: optional. One of `prerouting`, `postrouting`, or `postresponse`.
- `settings`: optional. Plugin-specific settings object (extra fields allowed).

**Response:**

- 200 OK: the resulting `PluginResponse` (`name`, `node`, `enabled`, `trigger`, `settings`).
- 500 Internal Server Error: failed to persist the configuration.
- 503 Service Unavailable: router not initialized.

## Delete Plugin

Endpoint:

```bash
DELETE /v1/plugins/{node}/{name}
```

**Example:**

```bash
curl -X DELETE http://localhost:8000/v1/plugins/dummy_logger/dummy
```

**Description:**

Removes a plugin instance, persists the change to the on-disk configuration, and
rebuilds the runtime.

**Response:**

- 200 OK:

  ```json
  {"status": "success", "message": "Plugin 'dummy' deleted"}
  ```

- 404 Not Found: no plugin with that `node`/`name`.
- 500 Internal Server Error: failed to delete the plugin.
- 503 Service Unavailable: router not initialized.

## Reset Plugin Instance

Endpoint:

```bash
POST /v1/plugins/{node}/{name}/reset
```

**Example:**

```bash
curl -X POST http://localhost:8000/v1/plugins/dummy_logger/dummy/reset
```

**Description:**

Resets one plugin instance's own runtime state (e.g. per-instance metrics) via
its `reset()` hook. Acts on the **live** plugin, so the instance must be loaded
(enabled). Applies only to plugins that support reset; a plugin that does not,
returns `400`.

**Response:**

- 200 OK:

  ```json
  {"status": "success", "message": "Reset plugin 'dummy'"}
  ```

- 400 Bad Request: the plugin does not support reset.

  ```json
  {"detail": "Plugin 'dummy' with node 'dummy_logger' does not support reset"}
  ```

- 404 Not Found: the plugin is not loaded.
- 503 Service Unavailable: router not initialized.

## Reset Plugin Node

Endpoint:

```bash
POST /v1/plugins/{node}/reset
```

**Example:**

```bash
curl -X POST http://localhost:8000/v1/plugins/dummy_logger/reset
```

**Description:**

Resets node-level (type/group-wide) state for a plugin type via its
`reset_node()` classmethod hook. Applies only to types that support it; a type
that does not, returns `400`.

**Response:**

- 200 OK:

  ```json
  {"status": "success", "message": "Reset plugin node 'dummy_logger'"}
  ```

- 400 Bad Request: the node does not support reset.
- 404 Not Found: `{node}` is not a registered plugin type.

## Policies

A **policy** is a named, ordered list of strategies plus a `criterion` that
decides how their results are combined during routing. Policies are stored in
`policy.yaml`; each policy is addressed by its unique `name`.

Classifier routing goes through a strategy whose rule is
`ModelBasedRule`: without `param` it serves the packaged soft version of the
default backbone, and switching routing behavior is a `POST` of the same
strategy or policy with another classifier `version` (see
[Strategies](#strategies)).

All policy endpoints target `<workspace>/policy.yaml`, which **must already
exist**: the API reads and edits an operator's workspace copy and never mutates
the bundled defaults in the source tree. Any request against a missing workspace
file returns `400`. Mutations are validated with the same rules applied at
startup and, on success, written atomically and **applied immediately**.

A policy object has the following structure:

```json
{
    "name": "Balanced",
    "criterion": "FirstMatch",
    "strategies": ["Planning", "ContextLengthQuality"]
}
```

- `name`: unique identifier. Restricted to letters, digits, `.`, `-`, and `_`.
- `criterion`: how strategy results are combined. One of `FirstMatch`
  (default) or `AllMatch`.
- `strategies`: non-empty, ordered list of strategy names. Each must name a
  strategy that exists in `strategy.yaml`.

### List Policies

Endpoint:

```bash
GET /v1/policies
```

**Example:**

```bash
curl http://localhost:8000/v1/policies
```

**Description:**

Lists all policies defined in `policy.yaml`.

**Response:**

- 200 OK:

  ```json
  [
      {
          "name": "Balanced",
          "criterion": "FirstMatch",
          "strategies": ["Planning", "ContextLengthQuality"]
      },
      {
          "name": "CostFirst",
          "criterion": "FirstMatch",
          "strategies": ["ZeroCost"]
      }
  ]
  ```

- 400 Bad Request: the workspace `policy.yaml` does not exist.
- 500 Internal Server Error: `policy.yaml` is invalid.

### Get Policy

Endpoint:

```bash
GET /v1/policies/{name}
```

**Example:**

```bash
curl http://localhost:8000/v1/policies/Balanced
```

**Description:**

Returns a single policy identified by its unique `name`.

**Response:**

- 200 OK: a single policy object (same structure as an entry in the list above).
- 404 Not Found: no policy with that `name`.

  ```json
  {"detail": "Policy 'Balanced' not found"}
  ```

### Create or Update Policy

Endpoint:

```bash
POST /v1/policies/{name}
```

**Example:**

```bash
curl http://localhost:8000/v1/policies/Balanced \
  -H "Content-Type: application/json" \
  -d '{
    "criterion": "FirstMatch",
    "strategies": ["Planning", "ContextLengthQuality"]
  }'
```

**Description:**

Creates or updates a policy, then persists the change to `policy.yaml`. The
policy is created if it does not exist, and replaced wholesale otherwise. The
`name` is taken from the path; a `name` in the body is ignored. A `GET`
response round-trips as a `POST` payload.

**Request Body:**

```json
{
    "criterion": "FirstMatch",
    "strategies": ["Planning", "ContextLengthQuality"]
}
```

- `criterion`: optional. `FirstMatch` (default) or `AllMatch`.
- `strategies`: **required**. Non-empty, ordered list of strategy names, each
  of which must exist in `strategy.yaml`.

**Response:**

- 200 OK: the resulting policy object. A classifier version the changed policy
  needs that cannot be loaded degrades (packaged default, then `-1`) instead of
  rejecting the change.
- 400 Bad Request: the body is invalid — e.g. missing or empty `strategies`, an
  invalid `criterion`, an invalid `name`, or a strategy that does not exist in
  `strategy.yaml`; or the workspace `policy.yaml` does not exist.

  ```json
  {"detail": "Policy 'Balanced' references unknown strategy 'Planing'"}
  ```

- 500 Internal Server Error: failed to persist `policy.yaml`.

### Delete Policy

Endpoint:

```bash
DELETE /v1/policies/{name}
```

**Example:**

```bash
curl -X DELETE http://localhost:8000/v1/policies/CostFirst
```

**Description:**

Removes a policy and persists the change to `policy.yaml`.

**Response:**

- 200 OK:

  ```json
  {"status": "success", "message": "Policy 'CostFirst' deleted"}
  ```

- 400 Bad Request: the workspace `policy.yaml` does not exist.
- 404 Not Found: no policy with that `name`.
- 409 Conflict: the policy is the router's active routing policy
  (`routing.policy`) and cannot be removed while in use.

  ```json
  {"detail": "Policy 'Balanced' is the active routing policy and cannot be deleted"}
  ```

- 500 Internal Server Error: failed to persist `policy.yaml`.

## Strategies

A **strategy** is a named rule set plus a provider selector: its rules decide
whether the strategy matches a request, and its `provider_selector` (and
optional `sort`) pick and rank the providers that can serve it. Strategies are
stored in strategy.yaml, and policies reference them by name.

`ModelBasedRule` turns a strategy into classifier routing: it scores the last
user message with a small model and the `provider_selector` maps the returned
index to providers.

```yaml
- name: ModelBasedRouting
  rules:
    - type: ModelBasedRule        # param optional: {model, version}
  provider_selector:
    label: {0: local, 1: cloud}
```

Without `param`, the rule serves the packaged soft version (`v1`, alias
`default`) of the default backbone. A soft version's trained data lives in the
backbone vocabulary -- soft vectors as the embedding rows of new soft tokens,
class rows as lm_head rows (ids continuing the original vocabulary) -- so the
router feeds plain token ids and reads the class logits by id. Versions are
`.rcv` files under `artifacts/router/<model>/`; `POST`ing a strategy with
another `version` switches to it after validation, and `GET` reports the
serving version plus `status` (`ok` / `degraded` / `unverified`). Soft
versions need an FP16/BF16 IR.

All strategy endpoints target `<workspace>/strategy.yaml`, which **must already
exist**: the API reads and edits an operator's workspace copy and never mutates
the bundled defaults in the source tree. Any request against a missing workspace
file returns `400`. Mutations are validated with the same rules applied at
startup and, on success, written atomically and **applied immediately**.

A strategy object has the following structure:

```json
{
    "name": "Planning",
    "description": "Routes based on message content indicating planning intent.",
    "rules": [
        {"type": "MessageContentRule", "param": {"pattern": "plan", "roles": ["user"]}}
    ],
    "provider_selector": {
        "label": "planning",
        "capability": {"complexity": 0.7}
    },
    "sort": [],
    "require_healthy": false,
    "limit": null
}
```

- `name`: unique identifier. Restricted to letters, digits, `.`, `-`, and `_`.
- `description`: optional free-text description.
- `rules`: optional list of `{type, param}` rule entries. `type` must be a
  built-in rule (see [Built-in Rules](./routing.md#built-in-rules));
  `param` holds that rule's constructor arguments. A strategy with no rules
  always matches.
- `provider_selector`: **required**. Criteria for selecting providers —
  `label`, `cost`, and `capability` (`complexity`, `tool_calling`). Scalars
  apply unconditionally; mappings are keyed by the zone index produced by a
  zone rule.
- `sort`: optional list of `{provider_attribute, descending}` entries that rank
  matched providers.
- `require_healthy`: optional. When `true`, only providers passing a live
  health check are considered.
- `limit`: optional integer cap on the number of ranked candidates returned.

### List Strategies

Endpoint:

```bash
GET /v1/strategies
```

**Example:**

```bash
curl http://localhost:8000/v1/strategies
```

**Description:**

Lists all strategies defined in `strategy.yaml`. A `ModelBasedRule` carries a
read-only `prompt_info` (see [Get Strategy](#get-strategy)).

**Response:**

- 200 OK:

  ```json
  [
      {
          "name": "Planning",
          "description": "Routes based on message content indicating planning intent.",
          "rules": [
              {"type": "MessageContentRule", "param": {"pattern": "plan", "roles": ["user"]}}
          ],
          "provider_selector": {"label": "planning", "capability": {"complexity": 0.7}},
          "sort": [],
          "require_healthy": false,
          "limit": null
      }
  ]
  ```

- 400 Bad Request: the workspace `strategy.yaml` does not exist.
- 500 Internal Server Error: `strategy.yaml` is invalid.

### Get Strategy

Endpoint:

```bash
GET /v1/strategies/{name}
```

**Example:**

```bash
curl http://localhost:8000/v1/strategies/Planning
```

**Description:**

Returns a single strategy, identified by its unique `name`.

A `ModelBasedRule` in the response carries a read-only `prompt_info` with its
current classifier status. `prompt_info` is ignored on `POST`, so a `GET`
result can be edited and posted back. The single-strategy endpoint also
includes a top-level `classifier_options` catalog with the available models
and versions; the strategy list omits this catalog to avoid repeating it for
every strategy.

```json
{
    "name": "Triage",
    "rules": [{
        "type": "ModelBasedRule",
        "param": {"model": "qwen35-2b", "version": "v2"},
        "prompt_info": {
            "kind": "hard", "status": "ok", "effective": "v2", "reason": null
        }
    }],
    "classifier_options": [{
        "model": "qwen35-2b",
        "versions": [
            {"version": "v1", "kind": "soft"},
            {
                "version": "v2",
                "kind": "hard",
                "text": "Classify the request. local: simple tasks. cloud: hard tasks."
            }
        ]
    }],
    "provider_selector": {"label": {"0": "local", "1": "cloud"}},
    "sort": [],
    "require_healthy": false,
    "limit": null
}
```

- `kind: "prompt_file"` identifies a multi-class prompt-file rule; its path,
  labels and threshold remain in the rule's `param`.
- `status`:
  - `ok`: the strategy is in the active policy and its version is serving.
  - `degraded`: the version could not be loaded. `effective` is the version
    serving in its place (the packaged default), or `null` when the rule
    matches nothing; `reason` says why.
  - `unverified`: the strategy is not in the active policy, so its version is
    not loaded or fully checked yet.
- `classifier_options`: returned by `GET /v1/strategies/{name}` only and
  omitted when the strategy has no `ModelBasedRule`. Each model contains its
  available versions. A hard version includes the original prompt `text`
  extracted from its `.rcv`, without the answer format appended by the router;
  a soft version has no `text`. An unreadable version includes `kind: null`
  and an `error`.

To edit a hard prompt, find the selected model/version's `text` in
`classifier_options`, replace the rule's `param` with the edited `text`, and
`POST` the strategy back (see [Create or Update Strategy](#create-or-update-strategy)).

**Response:**

- 200 OK: a single strategy object (same structure as an entry in the list above).
- 404 Not Found: no strategy with that `name`.

  ```json
  {"detail": "Strategy 'Planning' not found"}
  ```

### Create or Update Strategy

Endpoint:

```bash
POST /v1/strategies/{name}
```

**Example:**

```bash
curl http://localhost:8000/v1/strategies/Planning \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Routes based on message content indicating planning intent.",
    "rules": [
      {"type": "MessageContentRule", "param": {"pattern": "plan", "roles": ["user"]}}
    ],
    "provider_selector": {"label": "planning", "capability": {"complexity": 0.7}}
  }'
```

**Description:**

Creates or updates a strategy, then persists the change to `strategy.yaml`. The
strategy is created if it does not exist, and replaced wholesale otherwise. The
`name` is taken from the path; a `name` in the body is ignored. A `GET`
response round-trips as a `POST` payload.

**Request Body:**

```json
{
    "description": "Routes based on message content indicating planning intent.",
    "rules": [
        {"type": "MessageContentRule", "param": {"pattern": "plan", "roles": ["user"]}}
    ],
    "provider_selector": {"label": "planning", "capability": {"complexity": 0.7}},
    "sort": [],
    "require_healthy": false,
    "limit": null
}
```

- `provider_selector`: **required**. See the object structure above.
- `description`, `rules`, `sort`, `require_healthy`, `limit`: optional.

**ModelBasedRule Classifier:**

A strategy may contain at most one `ModelBasedRule`. Its `param` selects the
classifier in one of these ways (`version`, `text` and `prompt_file` are
mutually exclusive):

| `param` | Classifier |
| --- | --- |
| none, or only `model` | The packaged default version of the backbone |
| `version` | An existing version: `vN` or `default` |
| `text` (+ optional `labels`, `threshold`, `note`) | A hard-prompt version packed from `text` |
| `prompt_file` (+ optional `labels`, `threshold`) | A multi-class prompt file; not a version |

With `text`, the router packs a hard classifier version from your prompt
text, on the backbone selected by `model`, and stores it as
`<IR_ARTIFACTS_DIR>/<model>/vN.rcv`. The same text, categories and threshold
on the same backbone reuse the existing version instead of creating a new one.
The categories follow the same rules as for `prompt_file`: `labels`, or else
the values of `provider_selector.label`, which must then be keyed `0..N-1`.
Describe each category by name; the router appends the answer format. The
`threshold` defaults to `0.7`, and `note` is recorded in the version.
`strategy.yaml` stores only `{model, version}`, never the text.

```bash
curl http://localhost:8000/v1/strategies/Triage \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [{"type": "ModelBasedRule", "param": {
      "text": "Classify the request. local: simple tasks. cloud: hard tasks.",
      "threshold": 0.7
    }}],
    "provider_selector": {"label": {"0": "local", "1": "cloud"}}
  }'
```

The version is checked before anything is written. If the strategy is in the
active policy, or a new version is packed, the router runs the full backbone
compatibility check (L1/L2/L3) and a warmup. Otherwise the router checks the
file format, L1 and L2 with the backbone's tokenizer alone, and runs the full
check when a policy that uses the strategy is activated.

The response then includes `prompt_result` and `reconcile`:

```json
{
    "name": "Triage",
    "rules": [{"type": "ModelBasedRule", "param": {"model": "qwen35-2b", "version": "v2"}}],
    "provider_selector": {"label": {"0": "local", "1": "cloud"}},
    "prompt_result": {
        "model": "qwen35-2b", "version": "v2", "kind": "hard",
        "created": true, "active": true, "previous": "v1",
        "content_hash": "sha256:…",
        "validation": {"format": "ok", "L1": "ok", "L2": "ok",
                       "L3_min_cos": 0.99999, "hard_head_min_cos": 0.99999},
        "warmup_ms": 70.0
    },
    "reconcile": {"loaded": ["qwen35-2b/v2"], "released": [], "elapsed_ms": 272.1}
}
```

- `created`: whether a new version file was written; `false` when an existing
  version was reused.
- `active`: whether the strategy is in the active policy.
- `previous`: the version the strategy used before, or `null`.
- `validation` / `warmup_ms`: the check results; `warmup_ms` is `null` when the
  full check did not run.
- `reconcile`: classifier versions loaded and released by applying the change.

**Response:**

- 200 OK: the resulting strategy object.
- 400 Bad Request: the body is invalid — e.g. a missing `provider_selector`, an
  unknown rule `type`, invalid rule `param` (including conflicting
  `ModelBasedRule` fields), or an invalid `name`; or the workspace
  `strategy.yaml` does not exist.

  ```json
  {"detail": "Unknown rule class 'MessageContntRule'"}
  ```

- 404 Not Found: the `ModelBasedRule` names an unknown `model` or a `version`
  that does not exist.
- 422 Unprocessable Entity: the classifier cannot be used. For example, no IR
  is configured for the backbone, or the version fails a compatibility check.
  Nothing is written.
- 500 Internal Server Error: failed to persist `strategy.yaml`.

### Delete Strategy

Endpoint:

```bash
DELETE /v1/strategies/{name}
```

**Example:**

```bash
curl -X DELETE http://localhost:8000/v1/strategies/Planning
```

**Description:**

Removes a strategy and persists the change to `strategy.yaml`. A strategy that
is still referenced by a policy cannot be deleted, to avoid leaving a policy
pointing at a missing strategy. Delete or update the referencing policy first,
then delete the strategy.

**Response:**

- 200 OK:

  ```json
  {"status": "success", "message": "Strategy 'Planning' deleted"}
  ```

- 400 Bad Request: the workspace `strategy.yaml` does not exist.
- 404 Not Found: no strategy with that `name`.
- 409 Conflict: the strategy is still referenced by one or more policies.

  ```json
  {"detail": "Strategy 'Planning' is referenced by policies: Balanced"}
  ```

- 500 Internal Server Error: failed to persist `strategy.yaml`.
