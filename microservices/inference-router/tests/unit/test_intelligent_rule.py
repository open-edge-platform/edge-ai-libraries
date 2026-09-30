# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for IntelligentRule using a stub classifier — no OpenVINO.

The rule wraps the intelligent-router E/H classifier. A stub classifier is
injected so these tests never load the OV model, mirroring intelligent-router's
own stub-based router tests.
"""

import asyncio
from pathlib import Path

import pytest

from src.exceptions import ConfigurationError
from src.models import ChatCompletionMessage, ChatCompletionRequest, ChatCompletionRole
from src.providers.base import ProviderAdapter, ProviderMetadata
from src.rsd.rule import IntelligentRule
from src.rsd.strategy import (
    ProviderSelector,
    RuleBinding,
    StrategyDefinition,
    StrategyExecutor,
    build_rule_instance,
)


class StubClassifier:
    """Returns a canned E/H result; records the text it was asked to classify."""

    def __init__(self, label: str, confidence: float):
        # Duck-typed ClassifyResult: the rule only reads .label / .confidence.
        self.label = label
        self.confidence = confidence
        self.seen: list[str] = []

    def classify(self, text: str):
        self.seen.append(text)
        return self


class MockProvider(ProviderAdapter):
    """Minimal provider for strategy tests."""

    async def chat(self, request):
        raise NotImplementedError()

    async def chat_stream(self, request):
        raise NotImplementedError()

    async def list_models(self):
        return [{"id": self.name}]


def _request(text) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="auto",
        messages=[ChatCompletionMessage(role=ChatCompletionRole.USER, content=text)],
    )


@pytest.mark.unit
def test_label_e_maps_to_index_0():
    rule = IntelligentRule(classifier=StubClassifier("E", 0.9))
    assert rule.evaluate(_request("extract fields from this CSV")) == 0


@pytest.mark.unit
def test_label_h_maps_to_index_1():
    rule = IntelligentRule(classifier=StubClassifier("H", 0.85))
    assert rule.evaluate(_request("research external data and derive ratios")) == 1


@pytest.mark.unit
def test_low_confidence_is_no_match():
    rule = IntelligentRule(classifier=StubClassifier("E", 0.50))
    assert rule.evaluate(_request("ambiguous task")) == -1


@pytest.mark.unit
def test_rule_takes_no_user_routing_params():
    # The E/H label scheme, confidence floor, and fallback behaviour are all
    # fixed internals, not routing config: the constructor rejects them as kwargs.
    with pytest.raises(TypeError):
        IntelligentRule(min_confidence=0.6, classifier=StubClassifier("E", 0.9))
    with pytest.raises(TypeError):
        IntelligentRule(label_zones={"E": 2, "H": 5}, classifier=StubClassifier("H", 0.9))
    with pytest.raises(TypeError):
        IntelligentRule(fallback_zone=1, classifier=StubClassifier("E", 0.9))


@pytest.mark.unit
def test_unknown_label_is_no_match():
    rule = IntelligentRule(classifier=StubClassifier("Z", 0.99))
    assert rule.evaluate(_request("x")) == -1


@pytest.mark.unit
def test_classifies_last_user_message_with_content_parts():
    stub = StubClassifier("H", 0.9)
    rule = IntelligentRule(classifier=stub)
    request = ChatCompletionRequest(
        model="auto",
        messages=[
            ChatCompletionMessage(role=ChatCompletionRole.USER, content="first"),
            ChatCompletionMessage(
                role=ChatCompletionRole.ASSISTANT, content="ignored"
            ),
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content=[{"type": "text", "text": "the real query"}],
            ),
        ],
    )
    rule.evaluate(request)
    assert stub.seen == ["the real query"]


@pytest.mark.unit
def test_registered_and_buildable_via_factory():
    # build_rule_instance passes params as kwargs to the rule class; injecting a
    # stub classifier keeps this OV-free.
    rule = build_rule_instance(
        "IntelligentRule",
        {"classifier": StubClassifier("E", 0.9)},
    )
    assert isinstance(rule, IntelligentRule)


@pytest.mark.unit
def test_model_path_resolves_from_ir_ov_model(tmp_path, monkeypatch):
    model_path = tmp_path / "Qwen3.5-2B-FP16"
    model_path.mkdir()
    monkeypatch.setenv("IR_OV_MODEL", str(model_path))

    assert IntelligentRule._resolve_ov_model_path() == str(model_path)


@pytest.mark.unit
def test_model_path_ignores_ir_model_dir(tmp_path, monkeypatch):
    legacy_model_path = tmp_path / "models" / "Qwen3.5-2B-FP16"
    legacy_model_path.mkdir(parents=True)
    monkeypatch.delenv("IR_OV_MODEL", raising=False)
    monkeypatch.setenv("IR_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")

    with pytest.raises(ConfigurationError, match="Set IR_OV_MODEL"):
        IntelligentRule._resolve_ov_model_path()


@pytest.mark.unit
def test_missing_model_degrades_to_inert(tmp_path, monkeypatch):
    # IntelligentRouting ships in the default strategy set, so a deployment
    # without the OV model must not crash at construction: the rule becomes
    # inert (classifier is None) and evaluate() returns -1 (no match).
    monkeypatch.delenv("IR_OV_MODEL", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")

    rule = IntelligentRule()  # must not raise
    assert rule.classifier is None
    assert rule.evaluate(_request("anything")) == -1


@pytest.mark.unit
def test_factory_build_without_model_is_inert(tmp_path, monkeypatch):
    # Mirrors loading the default strategy.yaml on a model-less deployment:
    # build_rule_instance must succeed and yield an inert rule, not raise.
    monkeypatch.delenv("IR_OV_MODEL", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")

    rule = build_rule_instance("IntelligentRule", {})
    assert isinstance(rule, IntelligentRule)
    assert rule.evaluate(_request("x")) == -1


@pytest.mark.unit
def test_strategy_selects_cloud_provider_for_index_1_query():
    """label H -> index 1 -> provider_selector.label{1}='cloud' -> cloud provider."""
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="IntelligentRouting",
        provider_selector=ProviderSelector(label={0: "local", 1: "cloud"}),
        rules=[
            RuleBinding(
                "IntelligentRule",
                IntelligentRule(classifier=StubClassifier("H", 0.95)),
            )
        ],
    )
    providers = [
        MockProvider("local-small", metadata=ProviderMetadata(labels=["local"])),
        MockProvider("cloud-big", metadata=ProviderMetadata(labels=["cloud"])),
    ]

    candidates = asyncio.run(executor.execute(_request("a query"), providers, definition))

    assert [c.provider.name for c in candidates] == ["cloud-big"]
