# Plugin Architecture Reference

Covers the plugin interface, registration, job lifecycle, and PluginVenv helpers.

---

## Table of Contents

1. [Plugin Interface (`interfaces.py`)](#plugin-interface)
2. [Plugin Registration (`__init__.py`)](#plugin-registration)
3. [PluginRegistry](#pluginregistry)
4. [ModelManager and Job Lifecycle](#modelmanager-and-job-lifecycle)
5. [PluginVenv Helpers](#pluginvenv-helpers)
6. [Plugin Activation Flow](#plugin-activation-flow)

---

## Plugin Interface

**File:** `src/core/interfaces.py`

All plugins extend `ModelDownloadPlugin` (abstract base class):

```python
class ModelDownloadPlugin(ABC):
    @property
    def plugin_name(self) -> str:
        """Unique lowercase identifier (e.g. 'huggingface'). Must match ModelHub enum value."""
        return self.__class__.__name__.lower()

    @property
    def plugin_type(self) -> str:
        """Either 'downloader' or 'converter'."""
        return "downloader"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        """Return True if this plugin handles the given hub/model combination."""
        return False

    @abstractmethod
    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        """Core download/conversion logic. Must return a dict with at least:
        {
            "model_name": str,
            "source": str,        # plugin_name
            "download_path": str, # host-visible path
            "success": bool
        }
        """

    # Optional hooks (only implement if needed):
    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """For parallel file-level downloading (e.g. large datasets)."""
        raise NotImplementedError

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """Download a single task from get_download_tasks."""
        raise NotImplementedError

    async def post_process(self, model_name, output_dir, downloaded_paths, **kwargs) -> Dict:
        """Called after all tasks complete. Default implementation returns basic info."""
```

**Plugin types:**
- `"downloader"` — fetches model files from a remote source
- `"converter"` — transforms existing model files (e.g. OpenVINO conversion)

---

## Plugin Registration

**File:** `src/plugins/__init__.py`

The `PLUGINS` dict maps plugin names to their module path and class name:

```python
PLUGINS = {
    'huggingface': ('src.plugins.huggingface_plugin', 'HuggingFacePlugin'),
    'ollama': ('src.plugins.ollama_plugin', 'OllamaPlugin'),
    'ultralytics': ('src.plugins.ultralytics_plugin', 'UltralyticsDownloader'),
    'openvino': ('src.plugins.openvino_plugin', 'OpenVINOConverter'),
    'geti': ('src.plugins.geti_plugin', 'GetiPlugin'),
    'hls': ('src.plugins.hls_plugin', 'HlsPlugin'),
    'pipeline-zoo-models': ('src.plugins.pipeline_zoo_models_plugin', 'PipelineZooModelsPlugin'),
}
```

**To register a new plugin**, add an entry to this dict:
```python
'myhub': ('src.plugins.myhub_plugin', 'MyHubPlugin'),
```

**Loading mechanism:** At startup, `__init__.py` reads the `ENABLED_PLUGINS` env var
(set from the `--plugins` flag in `entrypoint.sh`), injects each plugin's dedicated venv
site-packages into `sys.path`, imports the class, and exports it into the module namespace.
Plugins whose dependencies aren't installed are silently skipped.

---

## PluginRegistry

**File:** `src/core/plugin_registry.py`

`PluginRegistry` is instantiated once at app startup. It:

1. **Discovers** all exported plugin classes by scanning the `src.plugins` module
2. **Stores** them keyed by `plugin_type` → `plugin_name` → instance
3. **Checks activation** via `/opt/activated_plugins.env` (written by `entrypoint.sh`)

Key methods:

```python
# Find a plugin that can handle a request
plugin = registry.find_plugin_for_model(
    plugin_type="downloader",
    model_name="meta-llama/Llama-3.2-1B",
    hub="huggingface"
)

# Check if a plugin was activated at startup
is_available, reason = registry.check_plugin_dependencies("huggingface")
# Returns (False, "Plugin 'huggingface' was not activated...") if not enabled

# Get all plugin names of a type
names = registry.get_plugin_names("downloader")  # ["huggingface", "ollama", ...]
```

**Activation file format** (`/opt/activated_plugins.env`):
```
ACTIVATED_PLUGINS=huggingface,openvino
# or
ACTIVATED_PLUGINS=all
```

---

## ModelManager and Job Lifecycle

**File:** `src/core/model_manager.py`

`ModelManager` orchestrates all download and conversion jobs:

```
Job lifecycle:
  register_job() → status="queued"
       │
       ▼
  process_download() / process_conversion()
       │
       ├─ status="downloading" or "converting"
       │
       ├─ plugin.download(model_name, output_dir, **kwargs)
       │       ├─ success → status="completed", result stored
       │       └─ exception → status="failed", error stored
       │
       └─ job result in self._jobs[job_id]
```

**In-memory storage:** `self._jobs` is a plain dict — not persisted. Jobs are lost on restart.

**Parallel execution:** `ThreadPoolExecutor` runs plugin downloads concurrently. Ollama
serializes itself via `_ollama_download_lock`.

**Key kwargs passed to `plugin.download()`:**
```python
{
    "hf_token": os.getenv("HF_TOKEN"),
    "revision": model_request.revision,
    "type": model_request.type,
    "is_ovms": model_request.is_ovms,
    "config": model_request.config.model_dump() if model_request.config else {},
}
```

**Diagnosing a stuck job:**
```python
# In plugin code, ensure you are NOT blocking the event loop:
# BAD  — blocks event loop
result = requests.get(url)

# GOOD — non-blocking
result = await asyncio.to_thread(requests.get, url)
# or use aiohttp
```

---

## PluginVenv Helpers

**File:** `src/core/plugin_venv.py`

Each plugin can have a dedicated virtual environment at `/opt/.venv-<plugin>`.
Use these helpers in plugin code to run subprocess commands in the plugin's venv:

```python
from src.core.plugin_venv import get_plugin_venv_python, get_plugin_venv_env

# Get the venv Python executable
python = get_plugin_venv_python("openvino")  # e.g. "/opt/.venv-openvino/bin/python"

# Get an env dict with the venv activated (PATH, VIRTUAL_ENV set)
env = get_plugin_venv_env("openvino")

# Run a command in the plugin's venv
result = subprocess.run(
    [python, "scripts/export_model.py", "text_generation", ...],
    env=env,
    check=True
)
```

**Venv discovery:** Venv paths are stored in `/opt/plugin_venvs.env`:
```
PLUGIN_VENV_OPENVINO=/opt/.venv-openvino
PLUGIN_VENV_ULTRALYTICS=/opt/.venv-ultralytics
```

---

## Plugin Activation Flow

```
docker run ... --plugins huggingface,openvino
       │
       ▼
entrypoint.sh
  ├─ Writes /opt/activated_plugins.env:
  │    ACTIVATED_PLUGINS=huggingface,openvino
  ├─ Builds /opt/.venv-huggingface with huggingface-hub
  ├─ Builds /opt/.venv-openvino with optimum, nncf, ...
  └─ Writes /opt/plugin_venvs.env with venv paths
       │
       ▼
FastAPI startup (main.py)
  ├─ PluginRegistry.discover_plugins(src.plugins)
  │    └─ __init__.py loads plugin classes into globals
  └─ For each plugin: check_plugin_dependencies()
         └─ Reads /opt/activated_plugins.env → logs AVAILABLE/NOT AVAILABLE
```

**If a plugin is called but not activated:**
```
POST /models/download → hub=huggingface
  → check_plugin_dependencies("huggingface") → (False, "Plugin not activated")
  → HTTP 400 Bad Request
```
