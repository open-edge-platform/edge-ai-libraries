# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import inspect
import os
from typing import Any, Tuple, List
from .interfaces import ModelDownloadPlugin

class PluginRegistry:
    def __init__(self):
        self.plugins = {"downloader": {}, "converter": {}}
        self.activated_plugins = self._get_activated_plugins()

    def _get_activated_plugins(self) -> List[str]:
        """
        Get the list of plugins that were activated during container startup
        by reading the activation file written by the entrypoint script.
        
        Returns:
            list: List of activated plugin names, or ["all"] if all plugins are activated
        """
        activated_plugins_file = "/opt/activated_plugins.env"
        if os.path.exists(activated_plugins_file):
            with open(activated_plugins_file, 'r') as f:
                content = f.read().strip()
                # Parse ACTIVATED_PLUGINS=plugin1,plugin2,plugin3 or ACTIVATED_PLUGINS=all
                if content.startswith("ACTIVATED_PLUGINS="):
                    activated = content.replace("ACTIVATED_PLUGINS=", "").strip()
                    if activated.lower() == "all":
                        return ["all"]
                    else:
                        return [p.strip().lower() for p in activated.split(",") if p.strip()]
        return []

    def discover_plugins(self, plugins_package):
        """
        Discover and register all plugins in the given package.
        
        Args:
            plugins_package: The package containing plugin modules
        """
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
        """
        Get a specific plugin by type and name.
        
        Args:
            plugin_type: The type of plugin (downloader, converter, etc.)
            plugin_name: The name of the plugin
            
        Returns:
            The plugin instance or None if not found
        """
        return self.plugins.get(plugin_type, {}).get(plugin_name)

    def get_plugin_names(self, plugin_type: str) -> list:
        """
        Get all plugin names of a specific type.
        
        Args:
            plugin_type: The type of plugins to get names for
            
        Returns:
            List of plugin names
        """
        return list(self.plugins.get(plugin_type, {}).keys())

    def find_plugin_for_model(self, plugin_type: str, model_name: str, hub: str, **kwargs):
        """
        Find a plugin that can handle the specified model.
        
        Args:
            plugin_type: Type of plugin to search for
            model_name: Name of the model
            hub: The hub the model comes from
            **kwargs: Additional parameters to pass to the can_handle method
            
        Returns:
            Plugin instance that can handle the model or None
        """
        for plugin in self.plugins.get(plugin_type, {}).values():
            if hasattr(plugin, "can_handle") and plugin.can_handle(model_name, hub, **kwargs):
                return plugin
        return None
        
    def check_plugin_dependencies(self, plugin_name: str) -> Tuple[bool, str]:
        """
        Check if a plugin was activated during container startup.
        
        Args:
            plugin_name: Name of the plugin to check
        
        Returns:
            tuple: (bool, str) indicating if the plugin is available and reason if not
        """
        # Check if the plugin was activated during container startup
        if self.activated_plugins:
            if "all" not in self.activated_plugins and plugin_name.lower() not in self.activated_plugins:
                return False, f"Plugin '{plugin_name}' was not activated during container startup. Active plugins: {', '.join(self.activated_plugins)}"
        
        return True, ""
