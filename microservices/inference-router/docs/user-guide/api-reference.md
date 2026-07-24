# API Reference

The router exposes an OpenAI-compatible API. All examples assume the router is
running on `localhost:8000`.

## Service Info

Endpoint:

```bash
GET /
```

**Description:**

Returns service name, version, status, and a map of available endpoints.

**Response:**

- 200 OK:

  ```json
  {
      "name": "Inference Router API",
      "version": "1.0.0",
      "status": "running",
      "endpoints": {
          "health": "/health",
          "chat": "/v1/chat/completions",
          "models": "/v1/models",
          "metrics": "/v1/metrics"
      }
  }
  ```

## Health Check

Endpoint:

```bash
GET /health
```

**Description:**

Liveness check. Includes router initialization status and current concurrency
counters.

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

**Description:**

Lists every available model. One entry per enabled provider in `config.yaml`,
where `id` is the configured backend model name (the value clients pass in
`request.model` to route here) and `owned_by` is the provider name. Two
providers MAY share an `id` — they're distinguishable by `owned_by`, and
routing by model name picks the first such provider in config order; pass
the provider name in `request.model` to target the other. The response
always includes the virtual model `"auto"` for automatic routing.

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

**Description:**

OpenAI-compatible chat completion. Set `model` to a concrete ID to pin the
backend, or to `"auto"` for smart routing. Set `stream: true` for SSE
streaming.

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

- 400 Bad Request: unknown model name.
- 422 Unprocessable Entity: request validation failed.
- 429 Too Many Requests: concurrency limit reached.
- 500 Internal Server Error: inference or unexpected failure.
- 503 Service Unavailable: router not initialized.

## Metrics

Endpoint:

```bash
GET /v1/metrics
```

**Description:**

Aggregated routing, token, and latency metrics, bucketed by provider name.
Counters accumulate from process start (or the last `POST /v1/metrics/reset`)
across both streaming and non-streaming requests.

**Response:**

- 200 OK: object with three top-level sections:

  Each `by_provider` map is keyed by `"<model>@<provider>"` (the backend
  model id and the configured provider name). When one provider serves
  multiple models, or two providers expose the same model, each
  (model, provider) pair gets its own bucket so dashboards can disambiguate
  them. The field name remains `by_provider` for back-compat with
  pre-existing dashboards; only the key strings changed.

  - `routing_stats` — total request count and per-bucket request counts.
  - `token_metrics` — per-bucket input / output / total token counts plus
    `request_share` and `token_share` (fractions of the overall traffic), and
    an `overall` aggregate.
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
              "Qwen/Qwen3.5-9B@local": 8,
              "MiniMax-M2.7@cloud": 4
          }
      },
      "token_metrics": {
          "by_provider": {
              "Qwen/Qwen3.5-9B@local": {
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
          }
      },
      "latency_metrics": {
          "by_provider": {
              "Qwen/Qwen3.5-9B@local": {
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
