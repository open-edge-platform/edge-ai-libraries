
import importlib
import inspect
from typing import Dict, Type, Any
from .interfaces import ModelDownloadPlugin

class PluginRegistry:
    def __init__(self):
        self.plugins = {"downloader": {}, "converter": {}}

    def discover_plugins(self, plugins_package):
        for name in dir(plugins_package):
            attr = getattr(plugins_package, name)
            if inspect.ismodule(attr):
                for _, obj in inspect.getmembers(attr, inspect.isclass):
                    if issubclass(obj, ModelDownloadPlugin) and obj is not ModelDownloadPlugin:
                        plugin_instance = obj()
                        plugin_type = getattr(plugin_instance, "plugin_type", "downloader")
                        plugin_name = getattr(plugin_instance, "plugin_name", obj.__name__.lower())
                        self.plugins.setdefault(plugin_type, {})[plugin_name] = plugin_instance

    def get_plugin(self, plugin_type: str, plugin_name: str) -> Any:
        return self.plugins.get(plugin_type, {}).get(plugin_name)

    def get_plugin_names(self, plugin_type: str) -> list:
        return list(self.plugins.get(plugin_type, {}).keys())

    def find_plugin_for_model(self, plugin_type: str, model_name: str, hub: str, **kwargs):
        for plugin in self.plugins.get(plugin_type, {}).values():
            if hasattr(plugin, "can_handle") and plugin.can_handle(model_name, hub, **kwargs):
                return plugin
        return None
