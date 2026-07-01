---
name: model-download-dev
description: >
  Extend, test, and debug the Model Download microservice codebase.
  Use this skill when a developer wants to: add a new plugin to the microservice;
  write tests for a plugin (including mocking subprocess calls, async methods,
  or the Ollama server); debug a job stuck in "downloading" or "converting";
  understand the plugin interface or registration mechanism; trace how a request
  flows through ModelManager; extend the OpenVINO conversion parameters;
  or add a new ModelHub value. Trigger on phrases like "add plugin",
  "write test", "stuck job", "extend microservice", "plugin not working",
  "how does model_manager work", "mock subprocess", "register new hub".
argument-hint: >
  Describe what you want to build or debug (e.g. "add a ModelScope plugin that
  downloads models from modelscope.cn")
---

# Model Download Developer Skill

Help developers extend, test, and debug the Model Download microservice.

> Codebase root: `microservices/model-download/`

## When to Use

- Adding a new download or conversion plugin
- Writing unit tests for a plugin (subprocess mocking, async fixtures)
- Debugging a job stuck in `downloading` or `converting`
- Understanding how `ModelManager`, `PluginRegistry`, or `PluginVenv` work
- Extending the `ModelHub` enum or `Config` schema
- Tracing plugin activation and `ACTIVATED_PLUGINS` env flow

## Reference Lookup

| Reference | When to read |
|-----------|-------------|
| [plugin-architecture.md](./references/plugin-architecture.md) | Plugin interface contract, PluginRegistry, ModelManager, PluginVenv |
| [testing-patterns.md](./references/testing-patterns.md) | Subprocess mocking, async fixtures, conftest patterns, parametrize |

## Example Walkthroughs

| File | Covers |
|------|--------|
| [examples/new-plugin.md](./examples/new-plugin.md) | Step-by-step: create a new downloader plugin end-to-end |
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
    ├── __init__.py      ← PLUGINS dict — add your plugin class here
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

Read [plugin-architecture.md](./references/plugin-architecture.md) for full interface details,
then follow this sequence:

### Step 1 — Create the Plugin File

Create `src/plugins/<name>_plugin.py` implementing `ModelDownloadPlugin`:

```python
from src.core.interfaces import ModelDownloadPlugin
from src.utils.logging import logger
import os

class MyHubPlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "myhub"                    # must be unique, lowercase

    @property
    def plugin_type(self) -> str:
        return "downloader"               # or "converter"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        return hub.lower() == "myhub"

    async def download(self, model_name: str, output_dir: str, **kwargs) -> dict:
        hub_dir = os.path.join(output_dir, "myhub")
        os.makedirs(hub_dir, exist_ok=True)
        # ... download logic ...
        return {
            "model_name": model_name,
            "source": "myhub",
            "download_path": hub_dir,
            "success": True,
        }
```

### Step 2 — Register in `__init__.py`

Add your plugin class to `src/plugins/__init__.py`:

```python
from .myhub_plugin import MyHubPlugin

PLUGINS = {
    ...
    "myhub": MyHubPlugin,
}
```

### Step 3 — Add to `ModelHub` Enum

In `src/api/models.py`:
```python
class ModelHub(str, Enum):
    ...
    MYHUB = "myhub"
```

### Step 4 — Add Optional Dependencies

In `pyproject.toml`, add a new optional group:
```toml
[project.optional-dependencies]
myhub = ["myhub-sdk>=1.0"]
```

### Step 5 — Update `entrypoint.sh` (if the plugin needs a venv)

If your plugin requires isolated dependencies, use `PluginVenv` helpers or follow the
pattern in `hls_plugin.py`.

### Step 6 — Write Tests

See [examples/writing-tests.md](./examples/writing-tests.md) for test structure and mock patterns.

---

## Procedure: Debugging a Stuck Job

Read [plugin-architecture.md](./references/plugin-architecture.md) → "Job Lifecycle" section.

**Quick diagnosis checklist:**

```bash
# 1. Check service logs for exceptions
docker logs model-download 2>&1 | tail -100

# 2. Inspect the job status
curl -s http://localhost:8200/api/v1/jobs/<job-id>

# 3. Verify the plugin was activated
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
- `ACTIVATED_PLUGINS` check failed silently — verify plugin name matches exactly
