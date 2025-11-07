# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Import all plugins so they can be discovered
from src.plugins.ultralytics_plugin import UltralyticsDownloader
from src.plugins.huggingface_plugin import HuggingFacePlugin
from src.plugins.ollama_plugin import OllamaPlugin
from src.plugins.openvino_plugin import OpenVINOConverter
# Add any other plugins here
