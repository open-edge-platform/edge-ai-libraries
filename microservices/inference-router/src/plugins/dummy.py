# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Dummy plugin that prints when each phase fires — used to verify wiring."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Type

from fastapi import APIRouter
from pydantic import BaseModel

from src.models import ChatCompletionRequest, ChatCompletionResponse
from src.plugins.base import PluginBaseNode
from src.plugins.manager import register_plugin

logger = logging.getLogger(__name__)


class DummyLoggerSettings(BaseModel):
    """Settings schema for the dummy logger plugin."""

    label: str = ""


@register_plugin
class DummyLoggerPlugin(PluginBaseNode):
    """Prints which phase invoked it; passes request/response through unchanged.

    Also a reference for the per-instance runtime contract: it counts invocations
    per phase, folds them into ``describe`` (the ``GET /plugins/{node}/{name}``
    payload), and zeroes them on ``reset``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._counts = {"process_request": 0, "process_response": 0}

    @classmethod
    def plugin_type(cls) -> str:
        return "dummy_logger"

    @classmethod
    def settings_model(cls) -> Type[BaseModel]:
        return DummyLoggerSettings

    @classmethod
    def routes(cls) -> Optional[APIRouter]:
        """Reference implementation of the generic plugin endpoint registry.

        Exposes ``GET /v1/plugins/dummy_logger/ping`` to demonstrate a plugin
        contributing its own HTTP API. The app factory mounts this at startup
        (see ``src.api.app.create_app``); no central edit to the API layer.
        """
        router = APIRouter()

        @router.get("/plugins/dummy_logger/ping")
        async def ping() -> Dict[str, Any]:
            return {"node": cls.plugin_type(), "pong": True}

        return router

    async def process_request(
        self, request: ChatCompletionRequest, **kwargs: Any
    ) -> ChatCompletionRequest:
        self._counts["process_request"] += 1
        message = f"[dummy_logger] now at {self.trigger} (plugin={self.name!r}, model={request.model!r})"
        print(message, flush=True)
        logger.info(message)
        return request

    async def process_response(
        self, response: ChatCompletionResponse, **kwargs: Any
    ) -> ChatCompletionResponse:
        self._counts["process_response"] += 1
        message = f"[dummy_logger] now at {self.trigger} (plugin={self.name!r})"
        print(message, flush=True)
        logger.info(message)
        return response

    def describe(self) -> Dict[str, Any]:
        return {**super().describe(), "metrics": dict(self._counts)}

    def reset(self) -> bool:
        self._counts = {"process_request": 0, "process_response": 0}
        return True
