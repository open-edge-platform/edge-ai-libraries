# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib
import os

PLUGINS = {
    'ultralytics': ('src.plugins.ultralytics_plugin', 'UltralyticsDownloader'),
    'ollama': ('src.plugins.ollama_plugin', 'OllamaPlugin'),
    'huggingface': ('src.plugins.huggingface_plugin', 'HuggingFacePlugin'),
    'openvino': ('src.plugins.openvino_plugin', 'OpenVINOConverter'),
    'geti': ('src.plugins.geti_plugin', 'GetiPlugin'),
}

# Determine enabled plugins from ENABLED_PLUGINS env variable
enabled_plugins_env = os.getenv('ENABLED_PLUGINS', 'all').lower()
enabled_plugins = (
    set(PLUGINS.keys())
    if enabled_plugins_env == 'all'
    else {p.strip() for p in enabled_plugins_env.split(',')}
)

# Load enabled plugins
for plugin_name, (module_path, class_name) in PLUGINS.items():
    if plugin_name not in enabled_plugins:
        continue
    try:
        module = importlib.import_module(module_path)
        globals()[class_name] = getattr(module, class_name)
    except ImportError:
        # Silently skip if dependencies not installed
        pass
    except AttributeError as e:
        print(f"Warning: Failed to load plugin {plugin_name}: {e}")
