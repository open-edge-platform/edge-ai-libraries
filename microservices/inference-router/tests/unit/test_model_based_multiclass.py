# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ModelBasedRule in multi-class mode — no OpenVINO.

With ``labels`` + ``prompt_file`` the rule classifies into the user's own
categories: label order is the zone, each label gets an internal single-token
code (A, B, ...) and the answer key is appended to the user's prompt. The
classifier build is stubbed, so these tests never load the OV model.
"""

import asyncio
import math
from pathlib import Path

import pytest

from src.exceptions import ConfigurationError
from src.models import ChatCompletionMessage, ChatCompletionRequest, ChatCompletionRole
from src.providers.base import ProviderAdapter, ProviderMetadata
from src.rsd.engine.strategy import (
    ProviderSelector,
    RuleBinding,
    StrategyDefinition,
    StrategyExecutor,
    build_rule_instance,
    build_strategy_definition,
)
from src.rsd.model_based.rule import ModelBasedRule

LABELS = ["local", "cloud", "planning"]


class StubClassifier:
    """Returns a canned class index (None = abstain)."""

    def __init__(self, index):
        self.index = index

    def classify(self, text: str):
        return self


class MockProvider(ProviderAdapter):
    async def chat(self, request):
        raise NotImplementedError()

    async def chat_stream(self, request):
        raise NotImplementedError()

    async def list_models(self):
        return [{"id": self.name}]


def _request(text="x") -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="auto",
        messages=[ChatCompletionMessage(role=ChatCompletionRole.USER, content=text)],
    )


@pytest.fixture
def built(monkeypatch, tmp_path):
    """Stub the model path and the OV build; record the configs that would be built."""
    configs = []
    monkeypatch.setenv("GATEWAY_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(ModelBasedRule, "_resolve_ov_model_path", classmethod(lambda cls: "/model"))
    monkeypatch.setattr(
        "src.rsd.model_based.rule.build_classifier",
        lambda cfg: configs.append(cfg) or StubClassifier(2),
    )
    return configs


@pytest.mark.unit
def test_prompt_gets_the_answer_key_and_codes_stay_internal(built, tmp_path):
    (tmp_path / "p.txt").write_text("Classify the task into a category.\n", encoding="utf-8")
    rule = ModelBasedRule(labels=LABELS, prompt_file="p.txt", threshold=0.6)

    assert rule.evaluate(_request()) == 2  # the classifier's index is the zone
    (cfg,) = built
    assert cfg.labels == LABELS and cfg.label_tokens == ["A", "B", "C"]
    assert cfg.system_prompt.startswith("Classify the task into a category.")
    assert "A: local\nB: cloud\nC: planning" in cfg.system_prompt
    assert cfg.threshold == 0.6


@pytest.mark.unit
def test_labels_can_be_any_names(built, tmp_path):
    (tmp_path / "p.txt").write_text("Pick one.", encoding="utf-8")
    labels = ["local-small", "frontier cloud model", "planner"]
    ModelBasedRule(labels=labels, prompt_file="p.txt").ensure_classifier()
    assert built[0].labels == labels and built[0].label_tokens == ["A", "B", "C"]


@pytest.mark.unit
def test_absolute_prompt_path_is_used_as_is(built, tmp_path):
    prompt = tmp_path / "elsewhere" / "p.txt"
    prompt.parent.mkdir()
    prompt.write_text("Pick one.", encoding="utf-8")
    ModelBasedRule(labels=LABELS, prompt_file=str(prompt)).ensure_classifier()
    assert built[0].system_prompt.startswith("Pick one.")


@pytest.mark.unit
def test_same_prompt_and_labels_share_a_classifier(built, tmp_path):
    (tmp_path / "p.txt").write_text("Pick one.", encoding="utf-8")
    first = ModelBasedRule(labels=LABELS, prompt_file="p.txt")
    second = ModelBasedRule(labels=LABELS, prompt_file="p.txt")
    assert first.ensure_classifier() is second.ensure_classifier()
    other = ModelBasedRule(labels=LABELS, prompt_file="p.txt", threshold=0.9)
    assert other.ensure_classifier() is not first.classifier  # different decision parameters
    assert len(built) == 2


@pytest.mark.unit
def test_missing_prompt_file_degrades_to_inert(built):
    rule = ModelBasedRule(labels=LABELS, prompt_file="absent.txt")  # constructing does not read it
    assert rule.evaluate(_request()) == -1
    assert rule.classifier is None and not built


@pytest.mark.unit
def test_missing_model_degrades_to_inert(tmp_path, monkeypatch):
    monkeypatch.delenv("IR_OV_MODEL", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")
    rule = build_rule_instance("ModelBasedRule", {"labels": LABELS, "prompt_file": "p.txt"})
    assert isinstance(rule, ModelBasedRule)
    assert rule.evaluate(_request()) == -1


@pytest.mark.unit
@pytest.mark.parametrize(
    "params,match",
    [
        ({"labels": LABELS}, "needs 'prompt_file'"),
        ({"labels": ["only"], "prompt_file": "p.txt"}, "2-26 labels"),
        ({"labels": [f"c{i}" for i in range(27)], "prompt_file": "p.txt"}, "2-26 labels"),
        ({"labels": ["a", "a"], "prompt_file": "p.txt"}, "distinct"),
        ({"labels": "local,cloud", "prompt_file": "p.txt"}, "list of non-empty strings"),
        ({"labels": ["a", ""], "prompt_file": "p.txt"}, "list of non-empty strings"),
    ],
)
def test_invalid_params_are_rejected_at_construction(params, match):
    with pytest.raises(ConfigurationError, match=match):
        ModelBasedRule(**params)


@pytest.mark.unit
@pytest.mark.parametrize("threshold", [-0.1, 1.1, math.nan, math.inf, -math.inf, "0.7", True])
def test_threshold_must_be_a_finite_probability(threshold):
    with pytest.raises(ConfigurationError, match="between 0 and 1"):
        ModelBasedRule(labels=LABELS, prompt_file="p.txt", threshold=threshold)


@pytest.mark.unit
@pytest.mark.parametrize("threshold", [0, 1, 0.0, 1.0])
def test_threshold_accepts_probability_boundaries(threshold):
    rule = ModelBasedRule(labels=LABELS, prompt_file="p.txt", threshold=threshold)
    assert rule.threshold == threshold


@pytest.mark.unit
def test_threshold_defaults_to_0_7():
    assert ModelBasedRule(labels=LABELS, prompt_file="p.txt").threshold == 0.7


def _strategy(param, label):
    return build_strategy_definition(
        {
            "name": "MultiClass",
            "rules": [{"type": "ModelBasedRule", "param": param}],
            "provider_selector": {"label": label},
        }
    )


@pytest.mark.unit
def test_categories_default_to_the_provider_selector_labels(built, tmp_path):
    (tmp_path / "p.txt").write_text("Pick one.", encoding="utf-8")
    # JSON bodies key zones by strings; YAML may use ints -- both work.
    definition = _strategy({"prompt_file": "p.txt"}, {"0": "planning", "1": "local", "2": "cloud"})
    rule = definition.rules[0].rule
    assert rule.labels == ["planning", "local", "cloud"]  # zone i = label[i]
    rule.ensure_classifier()
    assert built[0].labels == ["planning", "local", "cloud"]
    assert built[0].label_tokens == ["A", "B", "C"]
    assert "A: planning\nB: local\nC: cloud" in built[0].system_prompt


@pytest.mark.unit
@pytest.mark.parametrize(
    "label,expected_zone",
    [
        ({0: "local", 2: "cloud"}, {"local": 0, "cloud": 2}),  # gap
        ({5: "cloud", 1: "local"}, {"local": 1, "cloud": 5}),  # any keys, any order
    ],
)
def test_selector_keys_are_free_the_rule_answers_with_them(label, expected_zone):
    definition = _strategy({"prompt_file": "p.txt"}, label)
    rule = definition.rules[0].rule
    assert rule.labels == ["local", "cloud"]  # categories in key order
    for position, name in enumerate(rule.labels):
        rule.bind_classifier(StubClassifier(position))
        assert rule.evaluate(_request()) == expected_zone[name]


@pytest.mark.unit
def test_gapped_selector_routes_to_the_decided_provider():
    definition = _strategy({"prompt_file": "p.txt"}, {0: "local", 2: "cloud"})
    definition.rules[0].rule.bind_classifier(StubClassifier(1))  # decides "cloud"
    providers = [
        MockProvider("local-small", metadata=ProviderMetadata(labels=["local"])),
        MockProvider("cloud-big", metadata=ProviderMetadata(labels=["cloud"])),
    ]
    candidates = asyncio.run(StrategyExecutor().execute(_request(), providers, definition))
    assert [c.provider.name for c in candidates] == ["cloud-big"]


@pytest.mark.unit
def test_explicit_labels_answer_with_their_position():
    definition = _strategy(
        {"prompt_file": "p.txt", "labels": ["local", "cloud"]}, {0: "local", 1: "cloud"}
    )
    rule = definition.rules[0].rule
    rule.bind_classifier(StubClassifier(1))
    assert rule.evaluate(_request()) == 1


@pytest.mark.unit
def test_explicit_labels_name_categories_differently_from_providers():
    # Two categories routed to the same provider label: only expressible with labels.
    definition = _strategy(
        {"prompt_file": "p.txt", "labels": ["easy", "hard", "plan"]},
        {0: "local", 1: "cloud", 2: "local"},
    )
    assert definition.rules[0].rule.labels == ["easy", "hard", "plan"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "label,match",
    [
        ("cloud", "must then map zones to provider labels"),  # fixed label: no categories
        ({0: "local", 1: "local"}, "must be distinct"),
        ({0: "local"}, "2-26 labels"),
    ],
)
def test_categories_from_an_unusable_selector_are_rejected(label, match):
    with pytest.raises(ConfigurationError, match=match):
        _strategy({"prompt_file": "p.txt"}, label)


@pytest.mark.unit
def test_threshold_needs_prompt_file_but_not_labels():
    rule = _strategy({"prompt_file": "p.txt", "threshold": 0.6}, {0: "a", 1: "b"}).rules[0].rule
    assert rule.threshold == 0.6
    with pytest.raises(ConfigurationError, match="'threshold' applies only with 'prompt_file'"):
        ModelBasedRule(threshold=0.6)


@pytest.mark.unit
def test_rule_outside_a_strategy_without_labels_stays_inert(built):
    rule = ModelBasedRule(prompt_file="p.txt")  # never saw a selector
    assert rule.evaluate(_request()) == -1 and not built


@pytest.mark.unit
def test_strategy_selects_provider_for_planning_query():
    """index 2 -> provider_selector.label{2}='planning' -> planning provider."""
    definition = StrategyDefinition(
        name="MultiClassModelBasedRouting",
        provider_selector=ProviderSelector(label={0: "local", 1: "cloud", 2: "planning"}),
        rules=[
            RuleBinding(
                "ModelBasedRule",
                ModelBasedRule(labels=LABELS, prompt_file="p.txt", classifier=StubClassifier(2)),
            )
        ],
    )
    providers = [
        MockProvider("local-small", metadata=ProviderMetadata(labels=["local"])),
        MockProvider("cloud-big", metadata=ProviderMetadata(labels=["cloud"])),
        MockProvider("planner", metadata=ProviderMetadata(labels=["planning"])),
    ]

    candidates = asyncio.run(StrategyExecutor().execute(_request(), providers, definition))
    assert [c.provider.name for c in candidates] == ["planner"]


@pytest.mark.unit
def test_negative_selector_keys_are_rejected():
    """-1 is the router's no-match sentinel: a category keyed -1 would be
    unreachable, and classifier abstention would be indistinguishable from it."""
    from src.exceptions import ConfigurationError

    rule = ModelBasedRule(prompt_file="p.txt")
    with pytest.raises(ConfigurationError, match="negative keys"):
        rule.configure_from_selector(
            ProviderSelector(label={-1: "fallback", 0: "local"}), "MultiClass"
        )
