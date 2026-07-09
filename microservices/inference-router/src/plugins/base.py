# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Base classes for request plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, ValidationError

from src.models import ChatCompletionRequest, ChatCompletionResponse


class PluginSchemaError(ValueError):
    """Raised when plugin settings fail schema validation."""


class PluginNode(ABC):
    """A process unit inside a plugin.

    Nodes are executed in list order and can be scoped to prerouting,
    postrouting, or postresponse phases.
    """

    def __init__(
        self,
        name: str,
        trigger: Literal["prerouting", "postrouting", "postresponse"],
    ):
        self.name = name
        self.trigger = trigger

    @abstractmethod
    async def process_request(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Process and return the (possibly modified) request."""


class RequestPlugin(ABC):
    """Base class for request-processing plugins."""

    def __init__(
        self,
        name: str,
        settings: Dict[str, Any],
        trigger: Literal["prerouting", "postrouting", "postresponse"] = "prerouting",
        nodes: Optional[List[Dict[str, Any]]] = None,
    ):
        self.name = name
        self.settings = settings
        self.trigger = trigger
        self.nodes = nodes or []
        self.parsed_settings = self.validate_settings(settings)

    @classmethod
    @abstractmethod
    def plugin_type(cls) -> str:
        """Unique plugin type key used in config."""

    @classmethod
    @abstractmethod
    def settings_model(cls) -> Type[BaseModel]:
        """Plugin-specific settings schema."""

    @classmethod
    def validate_settings(cls, settings: Dict[str, Any]) -> BaseModel:
        """Validate settings against plugin-specific schema."""
        model_cls = cls.settings_model()
        try:
            return model_cls(**settings)
        except ValidationError as exc:
            raise PluginSchemaError(
                f"Invalid settings for plugin type '{cls.plugin_type()}': {exc}"
            ) from exc

    @abstractmethod
    async def process_request(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Process and return the (possibly modified) request."""

    async def process_response(self, response: ChatCompletionResponse) -> ChatCompletionResponse:
        """Process and return the (possibly modified) response."""
        return response

    async def run_nodes(
        self,
        request: ChatCompletionRequest,
        nodes: List[PluginNode],
    ) -> ChatCompletionRequest:
        """Run nodes matching the plugin trigger in declaration order."""
        current = request
        for node in nodes:
            if node.trigger != self.trigger:
                continue
            current = await node.process_request(current)
        return current
