# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import glob as _glob
import importlib
import os
import sys

PLUGINS = {
    'ultralytics': ('src.plugins.ultralytics_plugin', 'UltralyticsDownloader'),
    'pipeline-zoo-models': ('src.plugins.pipeline_zoo_models_plugin', 'PipelineZooModelsPlugin'),
    'ollama': ('src.plugins.ollama_plugin', 'OllamaPlugin'),
    'huggingface': ('src.plugins.huggingface_plugin', 'HuggingFacePlugin'),
    'openvino': ('src.plugins.openvino_plugin', 'OpenVINOConverter'),
    'geti': ('src.plugins.geti_plugin', 'GetiPlugin'),
    'hls': ('src.plugins.hls_plugin', 'HlsPlugin'),
}

_PLUGIN_VENVS_FILE = "/opt/plugin_venvs.env"
_plugin_venv_cache: dict[str, str | None] = {}


def _get_plugin_site_packages(plugin_name: str) -> str | None:
    """Return the site-packages path for a plugin's dedicated venv, or None."""
    if plugin_name in _plugin_venv_cache:
        return _plugin_venv_cache[plugin_name]

    venv_path = os.getenv(f"PLUGIN_VENV_{plugin_name.upper()}")

    if not venv_path and os.path.exists(_PLUGIN_VENVS_FILE):
        key = f"PLUGIN_VENV_{plugin_name.upper()}="
        with open(_PLUGIN_VENVS_FILE) as f:
            for line in f:
                if line.startswith(key):
                    venv_path = line[len(key):].strip()
                    break

    result = None
    if venv_path:
        matches = _glob.glob(f"{venv_path}/lib/python*/site-packages")
        result = matches[0] if matches else None

    _plugin_venv_cache[plugin_name] = result
    return result


# Determine enabled plugins from ENABLED_PLUGINS env variable
enabled_plugins_env = os.getenv('ENABLED_PLUGINS', 'all').lower()
enabled_plugins = (
    set(PLUGINS.keys())
    if enabled_plugins_env == 'all'
    else {p.strip() for p in enabled_plugins_env.split(',')}
)

# Load enabled plugins, injecting each plugin's dedicated venv into sys.path
for plugin_name, (module_path, class_name) in PLUGINS.items():
    if plugin_name not in enabled_plugins:
        continue

    site_pkgs = _get_plugin_site_packages(plugin_name)
    _injected = site_pkgs is not None and site_pkgs not in sys.path
    if _injected:
        sys.path.insert(0, site_pkgs)

    try:
        module = importlib.import_module(module_path)
        globals()[class_name] = getattr(module, class_name)
    except ImportError:
        # Silently skip if dependencies not installed
        pass
    except AttributeError as e:
        print(f"Warning: Failed to load plugin {plugin_name}: {e}")
    finally:
        # Remove the injected entry so it does not affect other imports;
        # already-imported modules remain available via sys.modules.
        if _injected and site_pkgs in sys.path:
            sys.path.remove(site_pkgs)

