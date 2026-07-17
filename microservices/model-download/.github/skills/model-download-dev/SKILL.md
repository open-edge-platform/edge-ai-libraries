---
name: model-download-dev
description: >
  Extend, test, debug, or integrate the Model Download microservice codebase.
  Use this skill when a developer wants to: add a new plugin to the microservice;
  write tests for a plugin (including mocking subprocess calls, async methods,
  or the Ollama server); debug a job stuck in "downloading" or "converting";
  understand the plugin interface or registration mechanism; trace how a request
  flows through ModelManager; extend the OpenVINO conversion parameters; add a
  new ModelHub value; or embed model-download into an app, Docker Compose stack,
  Helm deployment, CI/CD flow, or startup path. Trigger on phrases like
  "add plugin", "write test", "stuck job", "extend microservice",
  "plugin not working", "how does model_manager work", "mock subprocess",
  "register new hub", "integrate model-download", "call the model-download API",
  "poll model job", or "mount downloaded models".
argument-hint: >
  Describe what you want to build or debug (e.g. "add a new downloader plugin
  for an internal model hub" or "wire model-download into our compose stack")
---

# Model Download Developer Skill

Help developers extend, test, debug, and integrate the Model Download microservice.

> Codebase root: `microservices/model-download/`

## When to Use

- Adding a new download or conversion plugin
- Writing unit tests for a plugin (subprocess mocking, async fixtures)
- Debugging a job stuck in `downloading` or `converting`
- Understanding how `ModelManager`, `PluginRegistry`, or `PluginVenv` work
- Extending the `ModelHub` enum or `Config` schema
- Tracing plugin activation and `ACTIVATED_PLUGINS` env flow
- Integrating model-download into a backend, gateway, Compose stack, Helm deployment, or CI/CD path
- Designing app-side download/conversion workflows around `/models/download` and `/jobs/{job_id}`
- Wiring model storage, health checks, plugin activation, and failure handling into a wider system

## Reference Lookup

| Reference | When to read |
|-----------|-------------|
| [plugin-architecture.md](./references/plugin-architecture.md) | Plugin interface contract, PluginRegistry, ModelManager, PluginVenv |
| [testing-patterns.md](./references/testing-patterns.md) | Subprocess mocking, async fixtures, conftest patterns, parametrize |
| [integration-patterns.md](./references/integration-patterns.md) | App-side architecture, request flow, polling, error handling, storage wiring |

## Example Walkthroughs

| File | Covers |
|------|--------|
| [examples/plugin-blueprint.md](./examples/plugin-blueprint.md) | Reusable skeleton for new downloader and converter plugins |
| [examples/new-downloader-plugin.md](./examples/new-downloader-plugin.md) | Step-by-step: wire a new downloader plugin end-to-end |
| [examples/writing-tests.md](./examples/writing-tests.md) | Unit test patterns for plugins with subprocess and async mocks |

---

## Plugin Architecture Summary

```
src/
├── api/
│   ├── main.py          ← FastAPI app, endpoints, job dispatch
│   └── models.py        ← Pydantic models, ModelHub enum, ModelType, Config
├── core/
│   ├── interfaces.py    ← ModelDownloadPlugin ABC (plugin_name, plugin_type, can_handle, download)
│   ├── model_manager.py ← Job lifecycle, ThreadPoolExecutor, status tracking
│   ├── plugin_registry.py ← Auto-discovery, activation check, find_plugin_for_model
│   └── plugin_venv.py   ← Per-plugin venv management
└── plugins/
    ├── __init__.py      ← PLUGINS tuple mapping — register module path + class name here
    ├── huggingface_plugin.py
    ├── ollama_plugin.py
    ├── openvino_plugin.py
    ├── ultralytics_plugin.py
    ├── geti_plugin.py
    ├── hls_plugin.py
    └── pipeline_zoo_models_plugin.py
```

---

## Procedure: Adding a New Plugin

Read [plugin-architecture.md](./references/plugin-architecture.md) first, then use the
examples in this order:

1. [examples/plugin-blueprint.md](./examples/plugin-blueprint.md) for the reusable class skeleton
2. [examples/new-downloader-plugin.md](./examples/new-downloader-plugin.md) for the end-to-end wiring steps
3. [examples/writing-tests.md](./examples/writing-tests.md) for the unit-test shape

The minimum set of surfaces that must stay aligned is:

1. `plugin_name` in the class
2. the key in `src/plugins/__init__.py`
3. the `ModelHub` enum value in `src/api/models.py`
4. the optional dependency extra in `pyproject.toml`
5. activation support in `docker/entrypoint.sh`

Use the current tuple-based plugin registration format:

```python
PLUGINS = {
    # ... existing entries ...
    "myhub": ("src.plugins.myhub_plugin", "MyHubPlugin"),
}
```

Important runtime detail:

- `ENABLED_PLUGINS` controls which modules are imported by `src/plugins/__init__.py`
- `ACTIVATED_PLUGINS` in `/opt/activated_plugins.env` is what `PluginRegistry` checks later

If the plugin is implemented but does not appear in `/api/v1/plugins`, assume one of those
registration or activation surfaces is out of sync before you assume the core plugin logic is wrong.

---

## Procedure: Integrating into an Application or Platform

Read [integration-patterns.md](./references/integration-patterns.md) first when the user is
embedding model-download into another service or deployment stack.

Start by identifying the integration role:

- **Provisioning service**: pre-download models during deployment or CI/CD
- **Runtime dependency**: app calls model-download on demand when a model is missing
- **Ops/admin service**: internal tooling triggers downloads and exposes status to operators

Prefer the public REST API as the integration boundary:

1. Check readiness with `GET /api/v1/health`
2. Submit work with `POST /api/v1/models/download?download_path=<subdir>`
3. Store the returned `job_id`
4. Poll `GET /api/v1/jobs/{job_id}` until `completed` or `failed`
5. Use the reported `download_path` or `conversion_path`

Before proposing code or deployment changes, capture these decisions:

| Concern | Decide |
|---------|--------|
| Trigger point | deploy time, app startup, first request, or admin action |
| Model source | huggingface, ollama, ultralytics, openvino, geti, pipeline-zoo-models, hls |
| Needed plugins | minimal `--plugins` list |
| Persistence | where `MODEL_PATH` lives and which services mount it |
| Completion model | synchronous wait in caller, async background job, or external orchestrator |
| Failure behavior | retry, fail startup, partial availability, or operator intervention |

Expected integration outputs include one or more of:

- an application architecture recommendation
- Docker Compose or Helm changes
- app-side client code for submit + poll + result handling
- env var, plugin, and storage/mount checklists
- a failure-handling and retry strategy

Ground recommendations in the current API, deployment scripts, and plugin activation flow.

---

## Procedure: Debugging a Stuck Job

Read [plugin-architecture.md](./references/plugin-architecture.md) → "Job Lifecycle" section.

**Quick diagnosis checklist:**

```bash
# 1. Check service logs for exceptions
docker logs model-download 2>&1 | tail -100

# 2. Inspect the job status
curl -s http://localhost:8200/api/v1/jobs/<job-id>

# 3. Verify the plugin was activated and discovered
curl -s http://localhost:8200/api/v1/plugins

# 4. Test the plugin in isolation
python3 -c "
import asyncio
from src.plugins.myhub_plugin import MyHubPlugin
p = MyHubPlugin()
result = asyncio.run(p.download('my-model', '/tmp/test'))
print(result)
"
```

Common causes of stuck jobs:
- Plugin raised an exception that was swallowed — check logs
- Plugin is blocking the event loop (use `asyncio.to_thread` for sync I/O)
- Lock held by a crashed previous job (Ollama `_ollama_download_lock`) — restart container
- Plugin was implemented but not activated — verify `docker/entrypoint.sh`, `ENABLED_PLUGINS`, and `ACTIVATED_PLUGINS`
