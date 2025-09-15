from .interfaces import ModelDownloadPlugin
from ..plugins.huggingface_plugin import HuggingFacePlugin
from ..plugins.ollama import OllamaPlugin

# Plugin registry
PLUGIN_REGISTRY = {
    "huggingface": HuggingFacePlugin(),
    "ollama": OllamaPlugin(),
}

def get_plugin(hub: str) -> ModelDownloadPlugin:
    if hub not in PLUGIN_REGISTRY:
        raise ValueError(f"No plugin registered for hub: {hub}")
    return PLUGIN_REGISTRY[hub]
