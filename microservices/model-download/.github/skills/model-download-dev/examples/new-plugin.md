# Example: Adding a New Plugin

## Scenario

Add a `modelscope` plugin that downloads models from [ModelScope](https://modelscope.cn),
following the same conventions as the existing plugins.

---

## Step 1 — Create the Plugin File

Create `src/plugins/modelscope_plugin.py`:

```python
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Dict, Any

from src.core.interfaces import ModelDownloadPlugin
from src.utils.logging import logger


class ModelScopePlugin(ModelDownloadPlugin):
    """Plugin for downloading models from ModelScope Hub."""

    @property
    def plugin_name(self) -> str:
        return "modelscope"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        return hub.lower() == "modelscope"

    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        from modelscope import snapshot_download as ms_snapshot_download

        revision = kwargs.get("revision")
        ms_token = kwargs.get("ms_token") or os.getenv("MODELSCOPE_TOKEN")

        hub_dir = os.path.join(output_dir, "modelscope")
        model_specific_path = os.path.join(hub_dir, model_name.replace("/", "_"))
        os.makedirs(model_specific_path, exist_ok=True)

        logger.info(f"Downloading ModelScope model {model_name} to {model_specific_path}")

        ms_snapshot_download(
            model_id=model_name,
            revision=revision,
            local_dir=model_specific_path,
            token=ms_token,
        )

        logger.info(f"ModelScope model {model_name} downloaded successfully.")

        host_path = hub_dir
        if host_path.startswith("/opt/models/"):
            host_prefix = os.getenv("MODEL_PATH", "models")
            host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

        return {
            "model_name": model_name,
            "source": "modelscope",
            "download_path": host_path,
            "success": True,
        }
```

---

## Step 2 — Register in `__init__.py`

In `src/plugins/__init__.py`, add to the `PLUGINS` dict:

```python
PLUGINS = {
    # ... existing entries ...
    'modelscope': ('src.plugins.modelscope_plugin', 'ModelScopePlugin'),
}
```

---

## Step 3 — Add `ModelHub` Enum Value

In `src/api/models.py`:

```python
class ModelHub(str, Enum):
    HUGGINGFACE = "huggingface"
    ULTRALYTICS = "ultralytics"
    PIPELINE_ZOO_MODELS = "pipeline-zoo-models"
    OLLAMA = "ollama"
    OPENVINO = "openvino"
    GETI = "geti"
    HLS = "hls"
    MODELSCOPE = "modelscope"   # ← add this
```

---

## Step 4 — Add Optional Dependencies to `pyproject.toml`

```toml
[project.optional-dependencies]
# ... existing groups ...
modelscope = [
    "modelscope>=1.9",
]
```

---

## Step 5 — Update `entrypoint.sh` (Docker venv)

In `docker/entrypoint.sh`, add a venv entry for `modelscope`:

```bash
case "$plugin" in
    huggingface)
        pip install $INSTALL_OPTS ".[huggingface]"
        ;;
    # ... existing cases ...
    modelscope)
        pip install $INSTALL_OPTS ".[modelscope]"
        ;;
esac
```

---

## Step 6 — Write Tests

Create `tests/unit/test_modelscope_plugin.py` — see [writing-tests.md](./writing-tests.md) for the full pattern.

---

## Step 7 — Verify End-to-End

```bash
# Start service with new plugin
source scripts/run_service.sh up --plugins modelscope --model-path $PWD/models

# Verify plugin is listed
curl -s http://localhost:8200/api/v1/plugins | python3 -m json.tool

# Submit a download job
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=ms-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "damo/nlp_structbert_backbone_base_std",
        "hub": "modelscope"
      }
    ]
  }'
```

---

## Checklist

- [ ] `plugin_name` matches the key in `PLUGINS` dict and `ModelHub` enum value
- [ ] `plugin_type` is `"downloader"` or `"converter"`
- [ ] `can_handle()` is case-insensitive for hub comparison
- [ ] `download()` creates `os.path.join(output_dir, plugin_name)` as `hub_dir`
- [ ] Return dict has `model_name`, `source`, `download_path`, `success` keys
- [ ] `download_path` uses host-visible path (replaces `/opt/models/` prefix)
- [ ] Entry added to `PLUGINS` dict in `__init__.py`
- [ ] `ModelHub` enum updated in `src/api/models.py`
- [ ] Optional deps group added to `pyproject.toml`
- [ ] Tests written and passing
