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
  - `standalone` — A **non-hook** phase: the instance is built (its settings are
    validated) and its routes are mounted, but it is **never run** in any
    request/response chain. Use it for route-only plugins whose work is driven by
    their own HTTP endpoints rather than the per-request pipeline (e.g.
    [`provider_management`](#provider_management-plugin)). Placing such a plugin
    in a real stage would add a no-op to that chain on every request.
- **Auto-discovery.** Every module under `src/plugins/` is imported at startup,
  so any class decorated with `@register_plugin` self-registers. There is **no
  central registry to edit** when adding a plugin.

Within a stage, instances run **sequentially in the order they appear** in
`config.yaml`; each one receives the output of the previous. `standalone` plugins
are exempt — they do not run in any stage.

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
  modified request (passthrough). Overrides must keep `**kwargs`: at the
  `postrouting` stage the router passes `provider_name` (the provider chosen for
  the request) and `metrics_values={"provider": provider_name}`.
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
| `provider_management` | any (route-only)               | Starts or stops a provider via an external Local Provider Manager; loads/unloads vLLM LoRA adapters. |
| `dummy_logger`        | any                            | Logs the stage where the plugin was invoked and serves as a plugin contract reference implementation. |


### `compressor` Plugin

Source: [src/plugins/compressor.py](../../src/plugins/compressor.py).

Reduces prompt tokens before the request reaches the backend, using the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
library (bundled in the router image). One `compressor` node covers every
compressor type; the type is chosen per instance through `settings.type`:

- `tool` — filters the request `tools` schema down to a relevant subset using a
  **tool predictor** (an OpenAI-compatible LLM endpoint).
- `harness` — compresses system or developer messages using a **compress server**.
- `context` — compresses the conversation context.

>  **Caution:** The context compressor is experimental and is disabled by default.



How it works:

- Compressors act upon **requests only**, so configure them in the `prerouting` or
  `postrouting` stage. At the `postresponse` stage, a compressor is a no-op
  (and logs a warning).
- All instances share caching and metrics aggregation. Compression runs in a
  worker thread to keep the event loop responsive.
- On any compression error, the request is returned **unmodified** — a failing
  compressor degrades gracefully rather than dropping the request.
- Metrics: `describe()` returns instance metrics; `describe_node()` also includes
  `overall.*` totals across compressors. Postrouting metrics are additionally
  grouped by provider under `metrics_by_keys`. Instance responses never include
  `overall.*`. See [Metrics Checking](./get-started.md#metrics-checking) for details.

Configuration example — a `tool` compressor at the `prerouting` stage, and
`harness` and `context` compressors at the `postrouting` stage.
`node` is always `compressor`; `settings.type` selects the compressor type:

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
        predictor_backend: "generative"
        score_threshold: 2.0
        placement: "schema"
        accumulate: true
  postrouting:
    - name: "compressor_harness"
      node: "compressor"
      enabled: true
      settings:
        type: "harness"
        profile: "openclaw"
        compress_server_url: "http://localhost:8001/compress"
        compress_rate: 0.5
        compress_min_chars: 200
        timeout: 60.0
        enable_quantum_lock: false
    - name: "compressor_context"
      node: "compressor"
      enabled: false
      settings:
        type: "context"
        protect_recent_tool_turns: 1
        large_result_stub: true
        large_result_stub_guidance: "legacy"
        large_result_min_tokens: 4000
        large_result_keep_tool_turns: 1
        compression_mode: "none"
  postresponse: []
```

The `tool` example above uses the large-model predictor (`Qwen/Qwen3.6-35B-A3B`).
To use the small-model predictor instead, point the `tool` compressor at a
reranker endpoint and select tools with `top_k`:

```yaml
plugins:
  prerouting:
    - name: "compressor_tool"
      node: "compressor"
      enabled: true
      settings:
        type: "tool"
        predictor_url: "http://localhost:8091/v1/rerank"
        predictor_model: "Qwen/Qwen3-Reranker-0.6B"
        predictor_backend: "reranker"
        top_k: 10
        placement: "schema"
        accumulate: true
```

The two configurations trade off differently: the small model is faster but
saves fewer tool tokens. `top_k` should be sized to the number of tools per
request. See the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
ToolCompressor configuration guide for measured results and how to choose K.

The backing services, which are the compress server and tool predictor, are **not**
part of the router — deploy them separately. See the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
repository for deployment and per-compressor behavior.

### `provider_management` Plugin

Source: [src/plugins/provider_management.py](../../src/plugins/provider_management.py).

This plugin lets the router drive an external **Local Provider Manager** — a
service that starts and stops serving backends (containers) on demand and exposes
an HTTP API (`POST /providers`, `DELETE /providers/{name}`). It contributes HTTP
routes rather than a request hook (its `process_request` hook is a passthrough).

The plugin controls the provider **services** only — it never reads or changes
the router's provider config. Whether the router routes to a service is up to you,
through the [providers API](./api-reference.md#create-or-update-provider)
(`POST` / `DELETE /v1/providers/{name}`). The two are independent: starting a
service does not register or enable a provider, and stopping one does not disable
or remove it.

The manager is a single service; give the plugin its base URL in a `plugins:`
entry under the `standalone` (non-hook) stage — it is route-only and must not run in
any request/response chain:

```yaml
plugins:
  standalone:                                       # non-hook: routes only
    - name: "provmgr"
      node: "provider_management"
      settings:
        manager_url: "http://localhost:9900"   # base URL of the Local Provider Manager
        # timeout: 1200                          # optional; seconds, for slow cold starts
```

**Start** — `POST /v1/providers/manage` with the manager's start-request body
(docker params: `name` / `image` / `entrypoint` / `env` / `volumes` /
`docker_args` / `command`). The service `name` travels in the body (there is no
`{name}` in the path — the manager keys the container on it). Optionally add
`health_endpoint` — a URL (reachable from the router) that answers 2xx once the
backend is ready, e.g. `http://localhost:24680/health` (vLLM) or
`http://localhost:24690/v2/health/ready` (OVMS).

The plugin forwards the docker params to `POST {manager_url}/providers`, which
runs `docker run -d` and records the result, and returns the manager's response
(e.g. a 500 if `docker run` fails). With `health_endpoint` set the plugin first
polls it until it answers 2xx — failing fast with 502 if the manager reports the
container stopped, or 504 after `management_timeout` — and on failure removes the
container through the manager.

```bash
# vllm backend
curl -s -XPOST localhost:8000/v1/providers/manage -H 'Content-Type: application/json' -d '{
  "name":"vllm-qwen35-9b",
  "image":"intel/llm-scaler-vllm:0.26.0-b2",
  "entrypoint":"vllm",
  "env":{"VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT":"1","ZE_AFFINITY_MASK":"0"},
  "volumes":{"/path/to/Qwen3.5-9B":"/llm/models/qwen3-5-9b"},
  "docker_args":["--privileged","--shm-size","32g","--device","/dev/dri",
                 "--group-add","992","--group-add","44","-p","24680:24680"],
  "command":["serve","/llm/models/qwen3-5-9b","--served-model-name","qwen3-5-9b",
             "--port","24680","--host","0.0.0.0", "--gpu-memory-util", "0.7",
             "--enforce-eager", "--max-model-len", "32768",
             "--enable-auto-tool-choice", "--enable_prefix_caching",
             "--reasoning-parser","qwen3","--tool-call-parser","qwen3_coder"],
  "health_endpoint":"http://localhost:24680/health"
}'

# ovms backend
curl -s -XPOST localhost:8000/v1/providers/manage -H 'Content-Type: application/json' -d '{
  "name":"ovms-qwen36-35b",
  "image":"openvino/model_server:latest-gpu",
  "volumes":{"/path/to/Qwen3.6-35B-A3B-INT4":"/models/qwen3-6-35b-a3b-int4"},
  "docker_args":["--user","1000:1000","--device","/dev/dri",
                 "--group-add","992","--group-add","44","-p","24690:24690"],
  "command":["--rest_port","24690","--model_repository_path","/models",
             "--source_model","qwen3-6-35b-a3b-int4","--task","text_generation",
             "--target_device","GPU","--reasoning_parser","qwen3","--tool_parser","qwen3coder"],
  "health_endpoint":"http://localhost:24690/v2/health/ready"
}'
```

**Route to the service** — once it is up, add (or enable) its provider through
the providers API; `model` and `settings.endpoint` must match what the container
serves:

```bash
# register + enable the vLLM service as a provider
curl -s -XPOST localhost:8000/v1/providers/vllm-qwen35-9b -H 'Content-Type: application/json' -d '{
  "type":"hosted_vllm",
  "model":"qwen3-5-9b",
  "enabled":true,
  "settings":{"endpoint":"http://localhost:24680/v1"}
}'

# an already-declared provider (e.g. enabled: false in config.yaml) only needs
curl -s -XPOST localhost:8000/v1/providers/ovms-qwen36-35b -H 'Content-Type: application/json' \
  -d '{"enabled":true}'
```

**Stop** — `DELETE /v1/providers/manage?name=<name>`. The plugin forwards
`DELETE {manager_url}/providers/{name}` and returns the manager's response. It
does not touch the router config, so disable (`{"enabled":false}`) or delete the
provider through the providers API first — otherwise the router keeps routing to
a backend that is gone. Conversely, `DELETE /v1/providers/{name}` only edits
config and does **not** stop the container.

**Inspect** — `GET /v1/providers/manage` proxies the manager's `GET /providers`
and returns its **live** view of every started backend (the recorded `docker run`
command and result, plus the current container state); add `?name=<name>` for a
single one. This reflects what is actually running at the manager, as opposed to
`GET /v1/providers`, which reports the router's provider configuration.

```bash
curl -s localhost:8000/v1/providers/manage                 # all started backends
curl -s "localhost:8000/v1/providers/manage?name=qwen3"    # one
```

**LoRA adapters** — `POST /v1/providers/manage/load_lora_adapter` and
`.../unload_lora_adapter` hot-swap LoRA adapters on a running `hosted_vllm`
provider (one present in the router config). Unlike the routes above they go
straight to the provider's vLLM server
(its `settings.endpoint`, with its `settings.auth`), not the manager: the body is
vLLM's (`lora_name` / `lora_path`) plus `provider`, which is stripped before
forwarding to vLLM's `/v1/load_lora_adapter` / `/v1/unload_lora_adapter`. The
backend must run with `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True` and `--enable-lora`.

```bash
curl -s -XPOST localhost:8000/v1/providers/manage/load_lora_adapter -H 'Content-Type: application/json' \
  -d '{"provider":"vllm-qwen35-9b","lora_name":"sql_adapter","lora_path":"/models/loras/sql"}'
curl -s -XPOST localhost:8000/v1/providers/manage/unload_lora_adapter -H 'Content-Type: application/json' \
  -d '{"provider":"vllm-qwen35-9b","lora_name":"sql_adapter"}'
```

Per-request overrides (start body only, stripped before forwarding together with
`health_endpoint`): `manager_url` overrides the configured base URL, and
`management_timeout` the timeout (seconds) for the manager call and for the
readiness wait.

The `/v1/providers/manage` routes are always mounted for the registered type; a
`plugins:` entry configures the `manager_url` they use. Start can also take it per
request, but stop and inspect read it only from the plugin settings.

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
the stage (`prerouting`, `postrouting`, `postresponse`, or `standalone` for a
route-only plugin) and set `node` to the type's `plugin_type()`:

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
