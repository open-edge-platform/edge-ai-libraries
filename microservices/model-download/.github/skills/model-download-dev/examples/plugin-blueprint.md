<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Plugin Blueprint

## Purpose

Use this as the starting point for any new Model Download plugin.

It is intentionally generic:

- no vendor-specific SDK assumptions
- no hub-specific environment variable names
- no example that overfits to one provider

Pair this with:

- [plugin-architecture.md](../references/plugin-architecture.md) for the loading and activation flow
- [writing-tests.md](./writing-tests.md) for the test patterns

---

## Minimal Downloader Blueprint

Create `src/plugins/<name>_plugin.py`:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
from typing import Any

from src.core.interfaces import ModelDownloadPlugin
from src.utils.logging import logger


class MyHubPlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "myhub"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        return hub.lower() == "myhub"

    async def download(self, model_name: str, output_dir: str, **kwargs) -> dict[str, Any]:
        revision = kwargs.get("revision")
        api_token = kwargs.get("api_token") or os.getenv("MYHUB_TOKEN")

        hub_dir = os.path.join(output_dir, self.plugin_name)
        model_specific_path = os.path.join(hub_dir, model_name.replace("/", "_"))
        os.makedirs(model_specific_path, exist_ok=True)

        logger.info("Downloading %s model %s", self.plugin_name, model_name)

        await asyncio.to_thread(
            download_from_provider,
            model_name=model_name,
            revision=revision,
            destination=model_specific_path,
            token=api_token,
        )

        host_path = hub_dir
        if host_path.startswith("/opt/models/"):
            host_prefix = os.getenv("MODEL_PATH", "models")
            host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

        return {
            "model_name": model_name,
            "source": self.plugin_name,
            "download_path": host_path,
            "success": True,
        }
```

Replace `download_from_provider(...)` with the provider SDK or subprocess call your plugin needs.

If `download_from_provider` comes from a dependency that is installed only in the plugin's
dedicated extra/venv, do **not** import it lazily inside `download()`. Plugin loading only
temporarily injects that venv into `sys.path`; later lazy imports can fail after the path is
removed. Prefer a module-level import (optionally guarded with `try/except ImportError` for
testability), or call the dependency through the plugin venv subprocess helpers.

---

## Minimal Converter Blueprint

If the plugin transforms an existing model instead of downloading it, use:

```python
class MyConverterPlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "myconverter"

    @property
    def plugin_type(self) -> str:
        return "converter"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        return hub.lower() == "myconverter" or kwargs.get("is_ovms", False)

    async def download(self, model_name: str, output_dir: str, **kwargs) -> dict[str, Any]:
        raise NotImplementedError(
            "Converter plugins should expose their conversion entry point explicitly."
        )
```

Match the converter style already used in `src/plugins/openvino_plugin.py`.

---

## Registration Surfaces

For a new plugin to work end-to-end, all of these must line up:

1. `plugin_name` in the class
2. the key in `src/plugins/__init__.py`
3. the `ModelHub` value in `src/api/models.py`
4. the plugin extra in `pyproject.toml`
5. startup activation support in `docker/entrypoint.sh`

If one of those surfaces uses a different string, discovery or activation usually breaks.

---

## Required Return Shape

A downloader should return at least:

```python
{
    "model_name": model_name,
    "source": "myhub",
    "download_path": "models/myhub",
    "success": True,
}
```

If the plugin fails in a controlled way and chooses not to raise, return:

```python
{
    "model_name": model_name,
    "source": "myhub",
    "success": False,
    "error": "clear failure reason",
}
```

---

## Design Rules

- Keep `plugin_name` lowercase and stable.
- Make `can_handle()` case-insensitive for the hub value.
- Use a hub-specific subdirectory under `output_dir`.
- Rewrite `/opt/models/...` to the host-visible `MODEL_PATH` prefix before returning paths.
- Wrap synchronous SDK or filesystem-heavy work with `asyncio.to_thread(...)` if the plugin method is async.
- Surface errors clearly instead of silently swallowing them.

---

## Activation Rules

Two different mechanisms matter:

- `ENABLED_PLUGINS` controls which modules `src/plugins/__init__.py` imports
- `ACTIVATED_PLUGINS` is written to `/opt/activated_plugins.env` and checked by `PluginRegistry`

That means code registration alone is not enough. The plugin must also be startable with:

```bash
source scripts/run_service.sh up --plugins myhub --model-path $PWD/models
```

---

## Quick Checklist

- [ ] plugin file created under `src/plugins/`
- [ ] tuple mapping added to `src/plugins/__init__.py`
- [ ] enum value added in `src/api/models.py`
- [ ] optional dependency extra added in `pyproject.toml`
- [ ] activation support added in `docker/entrypoint.sh`
- [ ] unit tests added in `tests/unit/test_<name>_plugin.py`
