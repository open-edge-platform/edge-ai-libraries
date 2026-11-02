# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ModelBasedRule using a stub classifier — no OpenVINO."""

import asyncio
from pathlib import Path

import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from src.exceptions import ConfigurationError
from src.models import ChatCompletionMessage, ChatCompletionRequest, ChatCompletionRole
from src.providers.base import ProviderAdapter, ProviderMetadata
from src.rsd.engine.strategy import (
    ProviderSelector,
    RuleBinding,
    StrategyDefinition,
    StrategyExecutor,
    build_rule_instance,
)
from src.rsd.model_based.rule import ModelBasedRule


class StubClassifier:
    """Returns a canned decision; records the text it was asked to classify."""

    def __init__(self, index, confidence: float = 0.9):
        # Duck-typed ClassifyResult: the rule only reads .index (None = abstain).
        self.index = index
        self.confidence = confidence
        self.seen: list[str] = []

    def classify(self, text: str):
        self.seen.append(text)
        return self


class StubRegistry:
    def __init__(self, classifier=None):
        self.classifier = classifier
        self.triggers = []

    def loaded(self, model, version):
        if self.classifier is None:
            return None
        return type("Binding", (), {"classifier": self.classifier})()

    def trigger(self, model, version):
        self.triggers.append((model, version))


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
def test_class_index_is_the_zone():
    # The selector maps zone 0 to local and zone 1 to cloud.
    assert ModelBasedRule(classifier=StubClassifier(0)).evaluate(_request("extract")) == 0
    assert ModelBasedRule(classifier=StubClassifier(1)).evaluate(_request("derive")) == 1


@pytest.mark.unit
def test_abstain_is_no_match():
    # The classifier applies the decision (threshold included); index None means it abstained.
    rule = ModelBasedRule(classifier=StubClassifier(None, 0.60))
    assert rule.evaluate(_request("ambiguous task")) == -1


@pytest.mark.unit
def test_rule_applies_no_confidence_floor_of_its_own():
    # A decided class is routed as-is, whatever its confidence.
    rule = ModelBasedRule(classifier=StubClassifier(0, 0.40))
    assert rule.evaluate(_request("decided with a low threshold")) == 0


@pytest.mark.unit
def test_rule_rejects_unknown_routing_params():
    # Only labels / prompt_file / threshold are routing config; the rest is fixed.
    with pytest.raises(TypeError):
        ModelBasedRule(min_confidence=0.6, classifier=StubClassifier(0))
    with pytest.raises(TypeError):
        ModelBasedRule(label_zones={"E": 2, "H": 5}, classifier=StubClassifier(1))
    with pytest.raises(TypeError):
        ModelBasedRule(fallback_zone=1, classifier=StubClassifier(0))


@pytest.mark.unit
def test_parameterless_rule_uses_packaged_v1_soft_version():
    rule = ModelBasedRule()

    assert rule.model == "qwen35-2b"
    assert rule.version == "v1"
    assert rule.registry_requirement == ("qwen35-2b", "v1")


@pytest.mark.unit
def test_threshold_is_not_a_parameter_of_the_default_classifier():
    with pytest.raises(ConfigurationError, match="'threshold' applies only with"):
        ModelBasedRule(threshold=0.55)


@pytest.mark.unit
def test_classifies_last_user_message_with_content_parts():
    stub = StubClassifier(1)
    rule = ModelBasedRule(classifier=stub)
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
        "ModelBasedRule",
        {"classifier": StubClassifier(0)},
    )
    assert isinstance(rule, ModelBasedRule)


@pytest.mark.unit
def test_former_name_intelligent_rule_is_rejected():
    # IntelligentRule was renamed to ModelBasedRule with no alias: a strategy
    # still using the old type name must fail loudly rather than load silently.
    with pytest.raises(ConfigurationError, match="IntelligentRule"):
        build_rule_instance("IntelligentRule", {})


def test_model_path_resolves_from_ir_ov_model(tmp_path, monkeypatch):
    model_path = tmp_path / "Qwen3.5-2B-FP16"
    model_path.mkdir()
    monkeypatch.setenv("IR_OV_MODEL", str(model_path))

    assert ModelBasedRule._resolve_ov_model_path() == str(model_path)


@pytest.mark.unit
def test_model_path_ignores_ir_model_dir(tmp_path, monkeypatch):
    legacy_model_path = tmp_path / "models" / "Qwen3.5-2B-FP16"
    legacy_model_path.mkdir(parents=True)
    monkeypatch.delenv("IR_OV_MODEL", raising=False)
    monkeypatch.setenv("IR_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")

    with pytest.raises(ConfigurationError, match="Set IR_OV_MODEL"):
        ModelBasedRule._resolve_ov_model_path()


@pytest.mark.unit
def test_unavailable_v1_version_degrades_to_inert():
    registry = StubRegistry()
    rule = ModelBasedRule(registry=registry)  # must not raise
    assert rule.classifier is None
    assert rule.evaluate(_request("anything")) == -1
    assert registry.triggers == [("qwen35-2b", "v1")]


@pytest.mark.unit
def test_factory_build_uses_v1_without_loading():
    rule = build_rule_instance("ModelBasedRule", {})
    assert isinstance(rule, ModelBasedRule)
    assert rule.registry_requirement == ("qwen35-2b", "v1")


@pytest.mark.unit
def test_classifier_loading_is_deferred_until_evaluation():
    classifier = StubClassifier(1)
    registry = StubRegistry()
    rule = ModelBasedRule(registry=registry)

    assert rule.classifier is None
    assert rule.evaluate(_request("first query")) == -1
    assert registry.triggers == [("qwen35-2b", "v1")]

    registry.classifier = classifier
    assert rule.evaluate(_request("second query")) == 1
    assert rule.evaluate(_request("third query")) == 1
    assert classifier.seen == ["second query", "third query"]


@pytest.mark.unit
def test_empty_user_text_does_not_load_classifier():
    registry = StubRegistry()
    rule = ModelBasedRule(registry=registry)

    assert rule.evaluate(_request("")) == -1
    assert not registry.triggers


@pytest.mark.unit
def test_strategy_selects_cloud_provider_for_index_1_query():
    """Index 1 selects provider_selector.label{1}='cloud'."""
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="ModelBasedRouting",
        provider_selector=ProviderSelector(label={0: "local", 1: "cloud"}),
        rules=[
            RuleBinding(
                "ModelBasedRule",
                ModelBasedRule(classifier=StubClassifier(1, 0.95)),
            )
        ],
    )
    providers = [
        MockProvider("local-small", metadata=ProviderMetadata(labels=["local"])),
        MockProvider("cloud-big", metadata=ProviderMetadata(labels=["cloud"])),
    ]

    candidates = asyncio.run(executor.execute(_request("a query"), providers, definition))

    assert [c.provider.name for c in candidates] == ["cloud-big"]


@pytest.mark.unit
def test_released_rule_answers_minus_one_without_rebinding():
    """An unload_first swap detaches the rule: it answers -1 and does not pull
    the old classifier back out of the registry (that would pin the runtime
    the swap is trying to free)."""
    registry = Mock()
    registry.loaded.return_value = SimpleNamespace(classifier=object())
    rule = ModelBasedRule(version="v2", registry=registry)
    rule.bind_classifier(SimpleNamespace(classify=lambda t: SimpleNamespace(index=None)))
    rule.release_classifier()

    assert rule.classifier is None
    assert rule.evaluate(_request("hello")) == -1
    registry.loaded.assert_not_called()  # no rebind from the released version
