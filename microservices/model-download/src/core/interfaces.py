# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

MAX_OVERRIDE_CREDENTIAL_LENGTH = 8 * 1024  # 8 KiB (Max Token Base64-encoded size. Ex:JWT)

class DownloadTask:
    """
    Represents a sub-task in a model download process.
    Used for parallel downloading of model files.
    """
    def __init__(self, file_id: str, url: str, destination: str):
        self.file_id = file_id
        self.url = url
        self.destination = destination


@dataclass(frozen=True)
class PluginConfigKey:
    """
    Declares one configuration value a plugin consumes.

    A configuration key maps to an environment variable of the same ``name``.
    Callers may override it per request; the environment variable stays as the
    fallback default. Keys flagged ``sensitive`` (tokens/passwords) must never
    be logged. Keys sharing a ``group`` are resolved together: if a request
    overrides any key in the group, the whole group is taken from the request
    (env values are not mixed in), and every ``required`` key in that group
    must be supplied.
    """
    name: str
    description: str = ""
    sensitive: bool = False
    required: bool = False
    group: Optional[str] = None


class ListingNotSupportedError(NotImplementedError):
    """Raised when a hub/plugin does not support listing models."""


class ListingAuthError(Exception):
    """Raised when listing fails because credentials are missing or invalid."""

class ModelDownloadPlugin(ABC):
    @property
    def plugin_name(self) -> str:
        """Return the name of the plugin"""
        return self.__class__.__name__.lower()
        
    @property
    def plugin_type(self) -> str:
        """Return the type of the plugin (downloader/converter)"""
        return "downloader"
    
    def can_handle(self, model_name: str,hub: str, **kwargs) -> bool:
        """
        Check if this plugin can handle the given model name.
        Plugins should override this to implement their specific logic.
        """
        return False

    def resolve_config(self, overrides: Optional[Dict[str, Any]] = None, hub: Optional[str] = None) -> Dict[str, Any]:
        """
        Resolve this plugin's declared config keys for a single request.

        Per-request ``overrides`` win over environment variables (the fallback).
        The returned mapping is a fresh local dict scoped to the caller, so
        values never persist globally or leak between requests. Unknown keys are
        rejected, and grouped keys are resolved together (see PluginConfigKey).
        """
        overrides = overrides or {}
        keys = self.hub_config_keys(hub)
        declared = {key.name: key for key in keys}

        # Reject any override key the plugin does not understand.
        for name in overrides:
            if name not in declared:
                allowed = ", ".join(sorted(declared)) or "(none)"
                raise ValueError(
                    f"Unknown override key '{name}' for hub '{hub}'. "
                    f"Allowed keys: {allowed}."
                )

        # Reject excessively large override values.
        for name, override_val in overrides.items():
            if override_val is not None and len(override_val) > MAX_OVERRIDE_CREDENTIAL_LENGTH:
                raise ValueError(
                    f"override_credentials['{name}'] exceeds the maximum allowed "
                    f"length of {MAX_OVERRIDE_CREDENTIAL_LENGTH} characters"
                )

        # Groups that the request is overriding (any member supplied).
        touched_groups = {
            declared[name].group
            for name in overrides
            if overrides[name] is not None and declared[name].group
        }

        resolved: Dict[str, Any] = {}
        for key in keys:
            if key.name in overrides and overrides[key.name] is not None:
                resolved[key.name] = overrides[key.name]
            elif key.group and key.group in touched_groups:
                # The group is being overridden; never mix in the env value.
                if key.required:
                    raise ValueError(
                        f"When overriding '{key.group}' credentials, '{key.name}' "
                        f"must also be provided in the request."
                    )
                continue
            else:
                env_value = os.environ.get(key.name)
                if env_value is not None:
                    resolved[key.name] = env_value
        return resolved

    def plugin_supported_hubs(self) -> List[str]:
        """Return the list of hub names this plugin handles.

        Single-hub plugins return ``[self.plugin_name]`` (the default).
        Multi-hub plugins (e.g. external-sources) override this to return
        all the user-facing hub names they serve.
        """
        return [self.plugin_name]

    @property
    def supports_listing(self) -> bool:
        """Whether this plugin can list models available on its hub."""
        return False

    @property
    def listing_filter_fields(self) -> List[str]:
        """Filter fields supported by ``list_models`` for this plugin."""
        return []

    def _validate_listing_filters(self, filters: Optional[Dict[str, Any]]) -> None:
        """Reject any filter key not declared in ``listing_filter_fields``.

        Plugins with a fixed set of supported filters should call this at the
        start of ``list_models`` so unsupported keys fail loudly (raising
        ValueError) instead of being silently ignored.
        """
        if not filters:
            return
        allowed = set(self.listing_filter_fields)
        unknown = [key for key in filters if key not in allowed]
        if unknown:
            allowed_list = ", ".join(sorted(allowed)) or "(none)"
            raise ValueError(
                f"Unsupported filter(s): {', '.join(sorted(unknown))}. "
                f"Allowed filter(s): {allowed_list}."
            )

    def list_models(self, filters: Optional[Dict[str, Any]] = None, limit: int = 50, offset: int = 0, **kwargs) -> Dict[str, Any]:
        """
        List models available on this hub.

        Args:
            filters: Hub-specific filters (e.g. author/owner, search).
            limit: Maximum number of models to return.
            offset: Number of models to skip (pagination).

        Returns:
            A dict with ``items`` (list of model dicts) and ``total`` (int or None).

        Raises:
            ListingNotSupportedError: If the plugin does not support listing.
            ListingAuthError: If credentials are missing or invalid.
        """
        raise ListingNotSupportedError(
            f"Plugin '{self.plugin_name}' does not support listing models"
        )
        
    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """
        Get list of download tasks for a model.
        Used for parallel downloading.
        """
        raise NotImplementedError("This plugin does not support task-based downloading")
    
    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """
        Download a single task file.
        Used for parallel downloading.
        """
        raise NotImplementedError("This plugin does not support task-based downloading")
    
    async def post_process(self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs) -> Dict[str, Any]:
        """
        Post-process downloaded files.
        Called after all files have been downloaded.
        """
        # Default implementation just returns basic info
        return {
            "model_name": model_name,
            "download_path": output_dir,
            "success": True
        }
    
    def validate_credentials(
        self, resolved_config: Dict[str, Any], timeout: int = 5
    ) -> Dict[str, Any]:
        """Lightweight, idempotent credential pre-check.

        Called when the request sets ``validate_credentials: true``.  Plugins
        with sensitive config keys (tokens, passwords) override this to
        perform a cheap connectivity / auth check (e.g. ``whoami``) against
        the resolved credentials (override if provided, env otherwise).

        Plugins without sensitive keys (hls, ollama, ultralytics, etc.)
        inherit this default which returns "no credentials required".

        Returns:
            ``{"name": str, "ok": bool, "message": str}``
        """
        return {
            "name": "credentials",
            "ok": True,
            "message": (
                f"Credential validation is not applicable for hub "
                f"'{self.plugin_name}'; it has no credentials to validate. "
                "Only huggingface, geti, and openvino support this check."
            ),
        }

    def hub_config_keys(self, hub: str) -> List[PluginConfigKey]:
        """Return config keys applicable to a specific hub.

        Multi-hub plugins can override this to expose different keys per hub.
        Plugins without per-hub config can inherit this default.
        """
        return []

    @abstractmethod
    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        pass
