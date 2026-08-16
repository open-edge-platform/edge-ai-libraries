# Plugins

The router runs custom logic against each request/response through **plugins**.
A plugin can rewrite a request before routing, transform it after a provider is
picked, act on the response, or expose its own HTTP endpoints — without editing
the core API layer.

This page explains how the plugin system works, lists the plugins currently
implemented, and shows how to add and register a new one.

## Concepts

- **Plugin type (`node`).** A `PluginBaseNode` subclass, identified by its
  `plugin_type()` key. This key is the `node` you write in config and the API.
- **Plugin instance (`name`).** Each entry under `plugins` in `config.yaml` is
  one instance of a type. A type can have many instances with different
  settings; `name` is the unique instance identifier.
- **Stage (`trigger`).** When the instance runs in the request lifecycle:
  - `prerouting` — before provider selection (the routing decision).
  - `postrouting` — after provider selection, before the backend call.
  - `postresponse` — on the response after backend inference.
- **Auto-discovery.** Every module under `src/plugins/` is imported at startup,
  so any class decorated with `@register_plugin` self-registers. There is **no
  central registry to edit** when adding a plugin.

Within a stage, instances run **sequentially in the order they appear** in
`config.yaml`; each one receives the output of the previous.

## The plugin contract

A plugin subclasses `PluginBaseNode` (in [src/plugins/base.py](../../src/plugins/base.py)).
Only two methods are required; everything else has a safe default, so you
override only what you need.

**Required:**

- `plugin_type() -> str` — the unique `node` key.
- `settings_model() -> Type[BaseModel]` — a Pydantic schema for the instance's
  `settings`. Settings are validated at construction; invalid config is rejected
  with a `PluginSchemaError`.

**Optional hooks (defaults in parentheses):**

- `init()` — setup after settings are validated: build clients, register with
  shared managers, etc. (no-op).
- `process_request(request, **kwargs)` — act on the request; return the
  (possibly modified) request (passthrough).
- `process_response(response, **kwargs)` — act on the response (passthrough).
- `describe()` — the `GET /v1/plugins/{node}/{name}` payload; fold in
  per-instance runtime info, typically `{**super().describe(), "metrics": {...}}`
  (instance metadata).
- `describe_node()` — the `GET /v1/plugins/{node}` payload; expose type-wide
  aggregates spanning all instances (the node metadata).
- `reset()` / `reset_node()` — back `POST .../reset` for instance / node state
  (report "unsupported", HTTP 400).
- `health_check()` — probe backing dependencies (reports "unavailable").
- `routes()` — return a FastAPI `APIRouter` to mount under `/v1`, letting the
  plugin expose its own HTTP API without a central edit. Called once per type,
  regardless of instance count. Namespace paths as `/plugins/{node}/...` to
  avoid collisions (`None`).

## Currently implemented plugins

| `node`                | Stage(s)                    | What it does                                                        |
| --------------------- | --------------------------- | ------------------------------------------------------------------- |
| `compressor`          | `prerouting` / `postrouting`| Compresses prompts before the backend call to cut token usage.      |
| `provider_management` | any (route-only)            | Starts/stops a provider via an external Local Provider Manager.     |
| `dummy_logger`        | any                         | Logs which stage fired; a reference for the plugin contract.        |

### `compressor`

Source: [src/plugins/compressor.py](../../src/plugins/compressor.py).

Reduces prompt tokens before the request reaches the backend, using the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
library (bundled in the router image). One `compressor` node covers every
compressor kind; the kind is chosen per instance with `settings.type`:

- `tool` — filters the request `tools` schema down to a relevant subset using a
  **tool predictor** (an OpenAI-compatible LLM endpoint).
- `harness` — compresses system/developer messages using a **Lingua server**.
- `context` — compresses conversation context.

The available types come from the library (`available_compressor_types()`), and
each type's settings are validated against the library's own schema — unknown,
missing, or bad-enum params are rejected at load time.

How it works:

- Compressors act on **requests only**, so configure them in `prerouting` or
  `postrouting`. At `postresponse` a compressor is a no-op (and logs a warning).
- All instances share one process-wide `CompressionManager` for caching and
  metrics aggregation. The library makes *synchronous* blocking HTTP calls, so
  compression is offloaded to a worker thread to keep the event loop responsive.
- On any compression error the request is returned **unmodified** — a failing
  compressor degrades gracefully rather than dropping the request.
- Metrics: per-instance metrics fold into `describe()`; cross-instance
  `overall.*` metrics into `describe_node()`. See
  [Compression metrics](./get-started.md#metrics-checking) in the Quick Start
  for the metric fields and how to read compression savings.

Example configuration — a `tool` compressor at `prerouting` and a `harness`
compressor at `postrouting`. `node` is always `compressor`; `settings.type`
selects the kind, and the remaining `settings` are that kind's library params:

```yaml
plugins:
  prerouting:
    - name: "compressor_tool"
      node: "compressor"
      enabled: true
      settings:
        type: "tool"
        predictor_url: "http://localhost:8088/v1/chat/completions"
        predictor_model: "Qwen/Qwen3.6-35B-A3B"
        score_threshold: 2.0
        prompt_mode: "dynamic"
        tool_descriptions_mode: "dynamic"
        placement: "schema"
  postrouting:
    - name: "compressor_harness"
      node: "compressor"
      enabled: true
      settings:
        type: "harness"
        profile: "openclaw"
        lingua_url: "http://localhost:8001/compress"
        compress_rate: 0.5
        compress_min_chars: 200
        timeout: 60.0
        enable_quantum_lock: false
  postresponse: []
```

The backing services (Lingua server, tool predictor) are **not** part of the
router — deploy them separately. See the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
repository for deployment and per-compressor behavior.

### `provider_management`

Source: [src/plugins/provider_management.py](../../src/plugins/provider_management.py).

Lets the router drive an external **Local Provider Manager** that can start and
stop a backend on demand. This plugin contributes an HTTP route rather than a
request hook (its `process_request` is a passthrough).

A managed provider declares the manager URL in its `extra` block:

```yaml
providers:
  - name: "qwen3-local"
    type: "hosted_vllm"
    model: "Qwen/Qwen3.5-4B"
    enabled: false
    extra:
      management_endpoint: "http://localhost:9900/providers"
      # management_timeout: 1200   # optional; seconds, for slow cold starts
```

Callers then POST a tool-schema payload to `/v1/providers/{name}/manage`. The
body is forwarded **verbatim** to the manager (the router does not build or
validate the tool schema — the caller owns it). What the router *does* own is
reacting to the result:

- On a successful `start`, the provider is registered into the running config:
  `enabled` is flipped on and `type` / `model` / `settings.endpoint` are taken
  from the manager's `router_provider` block, while local `metadata` and `extra`
  are preserved.
- On a successful `stop`, the provider is un-registered by setting
  `enabled: false`; the entry (and its `extra`) is kept so it can be restarted.
- `list` / `status` commands and any failure leave the config untouched.

This plugin needs **no `plugins:` entry** — its `/v1/providers/{name}/manage`
route is mounted for the registered type at startup. All configuration lives in
the managed provider's `extra` block shown above.

### `dummy_logger`

Source: [src/plugins/dummy.py](../../src/plugins/dummy.py).

An example plugin that prints which stage invoked it and passes the
request/response through unchanged. It doubles as a reference for the runtime
contract: it counts invocations per stage, folds them into `describe()`, zeroes
them on `reset()`, and exposes a `routes()` endpoint
(`GET /v1/plugins/dummy_logger/ping`) demonstrating a plugin contributing its
own HTTP API. Use it to verify plugin wiring end to end.

Example configuration — the same instance can be placed in any stage; add it to
whichever stage(s) you want to trace:

```yaml
plugins:
  prerouting:
    - name: "logger_pre"
      node: "dummy_logger"
      enabled: true
      settings:
        label: "pre"
  postresponse:
    - name: "logger_post"
      node: "dummy_logger"
      enabled: true
      settings:
        label: "post"
```

## Registering a New Plugin

A plugin **type** is a `PluginBaseNode` subclass identified by its `node` key;
each entry in the config is one **instance** (`name`) of a type. Adding a type is
three steps — no central registry edit is needed, because every module under
`src/plugins/` is auto-discovered at startup.

**1. Drop a module in `src/plugins/`** (e.g. `src/plugins/word_count.py`) that
defines a settings schema and a plugin class decorated with `@register_plugin`:

```python
from typing import Any, Dict, Type
from pydantic import BaseModel
from src.models import ChatCompletionRequest
from src.plugins.base import PluginBaseNode
from src.plugins.manager import register_plugin


class WordCountSettings(BaseModel):
    prefix: str = "words"


@register_plugin
class WordCountPlugin(PluginBaseNode):
    """Counts words in the latest user message (example plugin)."""

    @classmethod
    def plugin_type(cls) -> str:        # the `node` key, must be unique
        return "word_count"

    @classmethod
    def settings_model(cls) -> Type[BaseModel]:
        return WordCountSettings

    def init(self) -> None:             # optional: setup with validated settings
        self._count = 0

    async def process_request(self, request: ChatCompletionRequest, **kwargs):
        text = request.messages[-1].content if request.messages else ""
        self._count += len(str(text).split())
        return request                  # return the (possibly modified) request

    def describe(self) -> Dict[str, Any]:   # optional: fold info into the GET
        return {**super().describe(), "metrics": {"words_seen": self._count}}

    def reset(self) -> bool:                # optional: back POST .../reset
        self._count = 0
        return True
```

Only `plugin_type()` and `settings_model()` are required. Everything else has a
safe default: `process_request`/`process_response` pass through, `describe()` /
`describe_node()` return metadata, `reset()` / `reset_node()` report "unsupported"
(HTTP 400), and `health_check()` reports healthy. Override just what you need.

**2. Configure an instance** under `plugins` in `workspace/config.yaml`, choosing
the stage (`prerouting`, `postrouting`, or `postresponse`) and setting `node` to
the type's `plugin_type()`:

```yaml
plugins:
  prerouting:
    - name: "counter"
      node: "word_count"
      enabled: true
      settings:
        prefix: "words"
```

**3. Verify** it registered and is serving:

```bash
curl http://localhost:8000/v1/plugins/nodes          # lists word_count + its schema
curl http://localhost:8000/v1/plugins/word_count/counter   # instance view + metrics
```

## Managing plugins at runtime

Because plugins are ordinary config entries, they can be listed, inspected,
created/updated, reset, and deleted at runtime through the `/v1/plugins` API —
changes are persisted to the on-disk config and take effect immediately. See the
[API Reference](./api-reference.md#list-plugins) for the full contract:

- `GET /v1/plugins` — list configured plugin instances.
- `GET /v1/plugins/nodes` — list plugin **types** registered in code.
- `GET /v1/plugins/{node}` and `GET /v1/plugins/{node}/{name}` — node- and
  instance-level views.
- `POST /v1/plugins/{node}/{name}` — create or update an instance.
- `DELETE /v1/plugins/{node}/{name}` — remove an instance.
- `POST /v1/plugins/{node}/reset` and `POST /v1/plugins/{node}/{name}/reset` —
  reset node- or instance-level state.

## Learn More

- The [Quick Start Guide](./get-started.md) covers enabling the compressor
  plugins and reading compression metrics.
- The [API Reference](./api-reference.md) documents every plugin endpoint.
