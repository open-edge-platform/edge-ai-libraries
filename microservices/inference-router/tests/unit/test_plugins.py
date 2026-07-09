# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for plugin system."""

from typing import Any, Dict

import pytest
from pydantic import BaseModel, Field, StrictStr

from src.config import PluginConfig
from src.models import (
    ChatCompletionRequest,
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionUsage,
)
from src.plugins.base import RequestPlugin
from src.plugins.manager import create_plugin_manager, register_plugin
from src.exceptions import ConfigurationError


class SamplePluginSettings(BaseModel):
    """Test plugin configuration schema."""

    enabled_tag: StrictStr = Field(default="test-plugin")
    annotate_extra_body: bool = Field(default=True)
    extra_config: Dict[str, Any] = Field(default_factory=dict)


@register_plugin
class SamplePlugin(RequestPlugin):
    """Test plugin used by plugin manager unit tests."""

    @classmethod
    def plugin_type(cls) -> str:
        return "test-plugin"

    @classmethod
    def settings_model(cls):
        return SamplePluginSettings

    async def process_request(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        if self.parsed_settings.annotate_extra_body:
            if request.extra_body is None:
                request.extra_body = {}

            request.extra_body.setdefault("plugins", {})
            request.extra_body["plugins"][self.name] = {
                "plugin_type": self.plugin_type(),
                "enabled_tag": self.parsed_settings.enabled_tag,
                "trigger": self.trigger,
                "extra_config": self.parsed_settings.extra_config,
            }
        return request


@pytest.mark.asyncio
async def test_plugins_run_by_trigger_around_rsd():
    """Plugins should run in trigger buckets around the RSD step."""
    plugin_manager = create_plugin_manager(
        [
            PluginConfig(
                name="pre-one",
                node="test-plugin",
                trigger="prerouting",
                settings={"enabled_tag": "pre-1", "annotate_extra_body": True},
            ),
            PluginConfig(
                name="post-one",
                node="test-plugin",
                trigger="postrouting",
                settings={"enabled_tag": "post-1", "annotate_extra_body": True},
            ),
        ]
    )

    request = ChatCompletionRequest(
        model="test-model",
        messages=[ChatCompletionMessage(role="user", content="hello")],
    )

    after_pre = await plugin_manager.process_prerouting_request(request)
    processed = await plugin_manager.process_postrouting_request(after_pre)

    assert processed.extra_body is not None
    assert "plugins" in processed.extra_body

    plugin_keys = list(processed.extra_body["plugins"].keys())
    assert plugin_keys == ["pre-one", "post-one"]


@pytest.mark.asyncio
async def test_plugin_schema_validation_per_plugin():
    """Each plugin validates settings by its own schema."""
    with pytest.raises(ConfigurationError):
        create_plugin_manager(
            [
                PluginConfig(
                    name="test-plugin-invalid",
                    node="test-plugin",
                    settings={"enabled_tag": 123},  # must be string
                )
            ]
        )


@pytest.mark.asyncio
async def test_unknown_plugin_node_rejected():
    """Unknown plugin nodes should fail fast during config load."""
    with pytest.raises(ConfigurationError):
        create_plugin_manager(
            [
                PluginConfig(
                    name="unknown-plugin",
                    node="unknown",
                    settings={},
                )
            ]
        )


@pytest.mark.asyncio
async def test_plugin_extra_config_is_exposed_in_output():
    """Plugin extra_config should be preserved in plugin annotation output."""
    plugin_manager = create_plugin_manager(
        [
            PluginConfig(
                name="test-plugin-pre",
                node="test-plugin",
                trigger="prerouting",
                settings={
                    "enabled_tag": "test-plugin-pre",
                    "annotate_extra_body": True,
                    "extra_config": {"feature_flag": True, "priority": 1},
                },
            ),
        ]
    )

    request = ChatCompletionRequest(
        model="test-model",
        messages=[ChatCompletionMessage(role="user", content="hello")],
    )

    processed = await plugin_manager.process_prerouting_request(request)

    assert processed.extra_body is not None
    plugin_payload = processed.extra_body["plugins"]["test-plugin-pre"]
    assert plugin_payload["trigger"] == "prerouting"
    assert plugin_payload["extra_config"] == {"feature_flag": True, "priority": 1}


@pytest.mark.asyncio
async def test_plugin_extra_config_validation_rejects_non_mapping():
    """extra_config must be a mapping according to plugin settings schema."""
    with pytest.raises(ConfigurationError):
        create_plugin_manager(
            [
                PluginConfig(
                    name="test-plugin-invalid-extra-config",
                    node="test-plugin",
                    trigger="prerouting",
                    settings={
                        "enabled_tag": "test-plugin-invalid",
                        "extra_config": "not-a-dict",
                    },
                )
            ]
        )


@pytest.mark.asyncio
async def test_postresponse_plugins_are_loaded_and_executed():
    """Postresponse plugins should be bucketed and invoked after provider response."""
    plugin_manager = create_plugin_manager(
        [
            PluginConfig(
                name="test-plugin-postresponse",
                node="test-plugin",
                trigger="postresponse",
                settings={
                    "enabled_tag": "postresponse",
                    "annotate_extra_body": True,
                },
            ),
        ]
    )

    assert len(plugin_manager.prerouting_plugins) == 0
    assert len(plugin_manager.postrouting_plugins) == 0
    assert len(plugin_manager.postresponse_plugins) == 1

    response = ChatCompletionResponse(
        id="resp-1",
        created=0,
        model="test-model",
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content="ok"),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )

    processed = await plugin_manager.process_postresponse_response(response)
    assert processed == response
