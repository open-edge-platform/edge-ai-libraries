# Plugins

The router runs custom logic against each request or response through **plugins**.
A plugin can rewrite a request before routing, transform it after a provider is
selected, act on the response, or expose its own HTTP endpoints — without editing
the core API layer.

This page explains how the plugin system works, lists the plugins currently
implemented, and shows how to add and register a new one.

## Concepts

- **Plugin type (`node`).** A `PluginBaseNode` subclass, identified by its
  `plugin_type()` key. This key is the `node` you write in the configuration and the API.
- **Plugin instance (`name`).** Each entry under `plugins` in `config.yaml` is
  one instance of a type. A type can have many instances with different
  settings; `name` is the unique instance identifier.
- **Stage (`trigger`).** Stages in the request lifecycle:
  - `prerouting` — When the plugin instance runs before provider selection, i.e.,
    before the routing decision is made.
  - `postrouting` — When the plugin instance runs after provider selection and before the
    backend call.
  - `postresponse` — When the plugin instance runs on the response after backend inference.
- **Auto-discovery.** Every module under `src/plugins/` is imported at startup,
  so any class decorated with `@register_plugin` self-registers. There is **no
  central registry to edit** when adding a plugin.

Within a stage, instances run **sequentially in the order they appear** in
`config.yaml`; each one receives the output of the previous.

## The Plugin Contract

The plugin subclass `PluginBaseNode` in [src/plugins/base.py](../../src/plugins/base.py)
implements the plugin contract in Inference Router. Only the following two methods are
required; everything else has a safe default, so you override only what you need.

**Required:**

- `plugin_type() -> str` — the unique `node` key.
- `settings_model() -> Type[BaseModel]` — a Pydantic schema for the instance's
  `settings`. Settings are validated at construction; invalid configuration is rejected
  with a `PluginSchemaError`.

**Optional hooks (defaults in parentheses):**

- `init()` — set up after the plugin instance's `settings` are validated; used to build
  clients, register with shared managers, and etc. (no-op).
- `process_request(request, **kwargs)` — acts on the request; returns the possibly
  modified request (passthrough).
- `process_response(response, **kwargs)` — acts on the response (passthrough).
- `describe()` — the `GET /v1/plugins/{node}/{name}` payload; folds in
  per-instance runtime info, typically `{**super().describe(), "metrics": {...}}`
  (instance metadata).
- `describe_node()` — the `GET /v1/plugins/{node}` payload; exposes type-wide
  aggregates spanning all instances (the node metadata).
- `reset()` and `reset_node()` — implement `POST .../reset` for the plugin-instance state
  and plugin-node state (report "unsupported", HTTP 400).
- `health_check()` — probes backing dependencies (reports "unavailable").
- `routes()` — returns a FastAPI `APIRouter` object to mount under `/v1`, letting the
  plugin expose its own HTTP API without modifying the central API layer. This method is
  called once per plugin type, regardless of instance count. Define plugin endpoints under
  the `/plugins/{node}/...` path namespace to avoid collisions (`None`).


## Currently Implemented Plugins

| `node`                | Stage(s)                       | What It Does                                                          |
| --------------------- | ------------------------------ | --------------------------------------------------------------------- |
| `compressor`          | `prerouting` and `postrouting` | Compresses prompts before the backend call to cut token usage.        |
| `provider_management` | any (route-only)               | Starts or stops a provider via an external Local Provider Manager.    |
| `dummy_logger`        | any                            | Logs the stage where the plugin was invoked and serves as a plugin contract reference implementation. |


### `compressor` Plugin

Source: [src/plugins/compressor.py](../../src/plugins/compressor.py).

Reduces prompt tokens before the request reaches the backend, using the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/libraries/adaptive-token-compressor)
library (bundled in the router image). One `compressor` node covers every
compressor type; the type is chosen per instance through `settings.type`:

- `tool` — filters the request `tools` schema down to a relevant subset using a
  **tool predictor** (an OpenAI-compatible LLM endpoint).
- `harness` — compresses system or developer messages using a **Lingua server**.
- `context` — compresses the conversation context.

The available types come from the library `available_compressor_types()`, and
each type's settings are validated against the library's own schema — unknown,
missing, or bad-enum params are rejected at load time.

How it works:

- Compressors act upon **requests only**, so configure them in the `prerouting` or
  `postrouting` stage. At the `postresponse` stage, a compressor is a no-op
  (and logs a warning).
- All instances share one process-wide `CompressionManager` for caching and
  metrics aggregation. The library makes *synchronous* blocking HTTP calls, so
  compression is offloaded to a worker thread to keep the event loop responsive.
- On any compression error, the request is returned **unmodified** — a failing
  compressor degrades gracefully rather than dropping the request.
- Metrics: Per-instance metrics are exposed via `describe()`; cross-instance
  `overall.*` metrics are exposed via `describe_node()`. See
  [Metrics Checking](./get-started.md#metrics-checking)
  for the metric fields and how to read compression savings.



Configuration example — a `tool` compressor at the `prerouting` stage and a `harness`
compressor at the `postrouting` stage. `node` is always `compressor`, `settings.type`
for the type, and the remaining `settings` are the type's library parameters:

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

The backing services, which are the Lingua server and tool predictor, are **not**
part of the router — deploy them separately. See the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/libraries/adaptive-token-compressor)
repository for deployment and per-compressor behavior.

### `provider_management` Plugin

Source: [src/plugins/provider_management.py](../../src/plugins/provider_management.py).

This plugin allows the router drive an external **Local Provider Manager** that can
start and stop a backend on demand. This plugin contributes an HTTP route rather
than a request hook (its `process_request` hook is a passthrough).

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

Callers then send a POST request with a tool-schema payload to `/v1/providers/{name}/manage`.
The body is forwarded **verbatim** to the manager (the router does not build or
validate the tool schema — the caller owns it). What the router *does* own is
reacting to the result:

- On a successful `start`, the provider is registered into the running configuration:
  `enabled` is flipped on and `type` , `model` , and `settings.endpoint` are taken
  from the manager's `router_provider` block, while local `metadata` and `extra`
  are preserved.
- On a successful `stop`, the provider is un-registered by setting
  `enabled: false`; the entry (and its `extra`) is kept so it can be restarted.
- The `list` and `status` commands, and any failure leave the configuration untouched.

This plugin needs **no `plugins:` entry** — its `/v1/providers/{name}/manage`
route is mounted for the registered type at startup. All configuration are located in
the managed provider's `extra` block shown above.

### `dummy_logger` Plugin

Source: [src/plugins/dummy.py](../../src/plugins/dummy.py).

A plugin example that prints the stage that invoked it, and passes the
request or response through, unchanged. It also serves as a reference implementation
for the runtime contract: it counts invocations per stage, exposes the counts through
`describe()`, resets them through `reset()`, and exposes a `routes()` endpoint
(`GET /v1/plugins/dummy_logger/ping`) to demonstrate a plugin contributing its
own HTTP API. Use it to verify that the plugin works end to end.

Configuration example — the same instance can be placed in any stage; add it to
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

## Register a New Plugin

A plugin **type** is a `PluginBaseNode` subclass identified by its `node` key;
each entry in the configuration is one **instance** (`name`) of a type. Adding
a type needs three steps — no central registry edit is needed, because every
module under `src/plugins/` is auto-discovered at startup.

**1. Create a module in `src/plugins/`** (e.g. `src/plugins/word_count.py`) that
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
safe default: `process_request` or `process_response` pass through, `describe()` or
`describe_node()` return metadata, `reset()` or `reset_node()` report "unsupported"
(HTTP 400), and `health_check()` reports healthy. Override just what you need.

**2. Configure an instance** under `plugins` in `workspace/config.yaml`. Choose
the stage (`prerouting`, `postrouting`, or `postresponse`) and set `node` to
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

**3. Verify** that the plugin has registered and is serving:

```bash
curl http://localhost:8000/v1/plugins/nodes          # lists word_count + its schema
curl http://localhost:8000/v1/plugins/word_count/counter   # instance view + metrics
```

## Manage Plugins at Runtime

Plugins are ordinary configuration entries, therefore they can be listed, inspected,
created or updated, reset, and deleted at runtime through the `/v1/plugins` API —
changes are persisted to the on-disk configuration and take effect immediately. See the
[API Reference](./api-reference.md#list-plugins) for the full contract:

- `GET /v1/plugins` — to list configured plugin instances.
- `GET /v1/plugins/nodes` — to list plugin **types** registered in code.
- `GET /v1/plugins/{node}` and `GET /v1/plugins/{node}/{name}` — to get node- and
  instance-level views.
- `POST /v1/plugins/{node}/{name}` — to create or update an instance.
- `DELETE /v1/plugins/{node}/{name}` — to remove an instance.
- `POST /v1/plugins/{node}/reset` and `POST /v1/plugins/{node}/{name}/reset` —
  to reset the node- or instance-level state.

## Learn More

- The [Get Started Guide](./get-started.md) section covers enabling the compressor
  plugins and reading compression metrics.
- The [API Reference](./api-reference.md) documents every plugin endpoint.
