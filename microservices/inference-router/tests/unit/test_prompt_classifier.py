# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PromptClassifier: soft / hard input construction and the zone decision — no OpenVINO.

The backbone runtime is faked: tokens embed to rows of a fixed table and the
"last hidden" is the embedding at the last position, so the expected class
probabilities can be computed by hand. Soft versions are token form: the fake
runtime is "patched" -- the soft and class rows are written into its table and
the class logits are its vocabulary logits read at the class ids.
"""

from __future__ import annotations

import numpy as np
from collections import OrderedDict
import pytest
from types import SimpleNamespace

from src.rsd.model_based.bundle import ClassifierBundle
from src.rsd.model_based.base import decide, zone_probs
from src.rsd.model_based.classifier import (
    OVQwenClassifier,
    PromptClassifier,
    hard_result,
    qwen_chat,
)
from src.exceptions import ConfigurationError
from src.rsd.model_based import settings
from src.rsd.model_based.settings import multiclass_classifier_config, resolve_ov_model_path
from src.rsd.model_based.vocab_tokens import VocabTokenPatch

H = 4
PAD_ID = 30
SOFT_IDS = [40, 41]  # free rows of the fake vocabulary
CLASS_START = 42  # class tokens right after the soft tokens


class FakeRuntime:
    hidden_size = H
    token_patch_digest = None

    def __init__(self):
        self.table = np.random.default_rng(0).normal(size=(64, H)).astype(np.float32)
        self.calls = []
        self.class_ids = None

    chat_style = "qwen"  # hard prompts render in the Qwen template

    def strip_prompt_prefix(self, ids):
        return np.asarray(ids, dtype=np.int64)  # no tokenizer-level prefix

    def encode(self, text):
        return np.array([ord(ch) % 29 for ch in text], dtype=np.int64)  # never PAD_ID

    def embed(self, ids):
        return self.table[np.asarray(ids)][None]

    def last_hidden(self, embeds, attention_mask=None):
        self.calls.append((embeds, attention_mask))
        return embeds[0, -1]

    def class_logits(self, embeds, attention_mask=None):
        self.calls.append((embeds, attention_mask))
        return self.table[self.class_ids] @ embeds[0, -1]  # vocab logits at the class ids


def _bundle(kind="soft", n_classes=12, **meta):
    rng = np.random.default_rng(1)
    base = {
        "version": "v7",
        "hidden": H,
        "num_classes": n_classes,
        "class_semantics": [f"c{i}" for i in range(n_classes)],
        "threshold": 0.5,
        "text_max_tokens": 6,
        "truncation_side": "left",
        "render": {
            "template": "raw",
            "soft_position": "before",
            "padding": {"between_soft_and_query": 3, "pad_token_id": PAD_ID},
        },
    }
    if kind == "soft":
        base.update(
            soft_token_ids=SOFT_IDS,
            label_token_ids=list(range(CLASS_START, CLASS_START + n_classes)),
        )
    if kind == "soft" and n_classes == 12:
        base.update(class_zones=[1] * 6 + [0] * 6, zone_names=["local", "cloud"])
    base.update(meta)
    return ClassifierBundle(
        kind=kind,
        prompt=rng.normal(size=(2, H)).astype(np.float32) if kind == "soft" else "Pick one.",
        head_weight=rng.normal(size=(n_classes, H)).astype(np.float32),
        head_bias=rng.normal(size=n_classes).astype(np.float32),
        fp_hidden=np.zeros((1, H), np.float32),
        meta=base,
    )


def _clf(bundle, rt, **kwargs):
    """The classifier, with a soft version's rows written into the fake runtime first."""
    if bundle.kind != "soft":
        return PromptClassifier(bundle, rt, **kwargs)
    patch = VocabTokenPatch(
        tuple(bundle.soft_token_ids), bundle.prompt, tuple(bundle.label_token_ids),
        bundle.head_weight,
    )
    rt.table[list(patch.soft_ids)] = patch.soft_rows
    rt.table[list(patch.label_ids)] = patch.label_rows
    rt.class_ids, rt.token_patch_digest = list(patch.label_ids), patch.digest
    return PromptClassifier(bundle, rt, vocab_patch=patch, **kwargs)


def _class_probs(bundle, hidden):
    logits = bundle.head_weight.astype(np.float64) @ hidden + bundle.head_bias
    e = np.exp(logits - logits.max())
    return e / e.sum()


@pytest.mark.unit
def test_soft_input_is_soft_then_masked_pads_then_query():
    rt, bundle = FakeRuntime(), _bundle()
    _clf(bundle, rt).classify("abcd")
    ((embeds, mask),) = rt.calls
    query = rt.encode("abcd")
    np.testing.assert_array_equal(embeds[0, :2], bundle.prompt)
    np.testing.assert_array_equal(embeds[0, 2:5], rt.table[[PAD_ID] * 3])
    np.testing.assert_array_equal(embeds[0, 5:], rt.table[query])
    assert mask.tolist() == [1, 1, 0, 0, 0, 1, 1, 1, 1]


@pytest.mark.unit
def test_query_is_truncated_from_the_left():
    rt = FakeRuntime()
    _clf(_bundle(), rt).classify("abcdefghij")  # 10 tokens, text_max_tokens 6
    embeds, mask = rt.calls[0]
    np.testing.assert_array_equal(embeds[0, 5:], rt.table[rt.encode("efghij")])
    assert mask.sum() == 2 + 6


@pytest.mark.unit
def test_classes_merge_into_zones_and_decide():
    rt, bundle = FakeRuntime(), _bundle()
    result = _clf(bundle, rt).classify("abcd")

    probs = _class_probs(bundle, rt.table[rt.encode("abcd")[-1]].astype(np.float64))
    p_local = probs[6:].sum()
    assert result.scores == pytest.approx({"local": p_local, "cloud": 1 - p_local})
    assert result.index == (0 if p_local >= 0.5 else 1)
    assert result.label == ["local", "cloud"][result.index]
    assert (result.kind, result.version, result.threshold) == ("soft", "v7", 0.5)
    assert result.raw["class_probs"] == pytest.approx(probs.tolist())


@pytest.mark.unit
def test_threshold_abstains():
    result = _clf(_bundle(threshold=1.0), FakeRuntime()).classify("abcd")
    assert result.index is None and result.label is None


@pytest.mark.unit
def test_multiclass_soft_routes_to_the_most_likely_class():
    rt, bundle = FakeRuntime(), _bundle(n_classes=3, class_semantics=["a", "b", "c"])
    result = _clf(bundle, rt).classify("abcd")
    probs = _class_probs(bundle, rt.table[rt.encode("abcd")[-1]].astype(np.float64))
    assert list(result.scores) == ["a", "b", "c"]
    assert result.index == int(np.argmax(probs)) and result.label == "abc"[result.index]


@pytest.mark.unit
def test_hard_version_renders_the_chat_template_without_mask():
    rt = FakeRuntime()
    bundle = _bundle(kind="hard", n_classes=2, class_semantics=["E", "H"])
    result = _clf(bundle, rt).classify("abcd")
    ((embeds, mask),) = rt.calls
    np.testing.assert_array_equal(embeds, rt.embed(rt.encode(qwen_chat("Pick one.", "abcd"))))
    assert mask is None
    assert list(result.scores) == ["E", "H"] and result.kind == "hard"


@pytest.mark.unit
def test_cache_holds_probabilities():
    rt = FakeRuntime()
    clf = _clf(_bundle(), rt)
    first = clf.classify("abcd")
    clf.threshold = 1.0  # decision parameters apply on a cache hit
    second = clf.classify("abcd")
    assert len(rt.calls) == 1
    assert second.scores == first.scores and second.index is None


@pytest.mark.unit
def test_backbone_must_match_the_version():
    rt = FakeRuntime()
    rt.hidden_size = H + 1
    with pytest.raises(ValueError, match="hidden"):
        _clf(_bundle(), rt)


@pytest.mark.unit
@pytest.mark.parametrize(
    "render,match",
    [
        ({"template": "qwen_chat"}, "unsupported soft render"),
        ({"template": "raw", "soft_position": "after"}, "unsupported soft render"),
        ({"template": "raw", "padding": {"between_soft_and_query": 64}}, "pad_token_id"),
    ],
)
def test_unsupported_soft_render_is_rejected(render, match):
    with pytest.raises(ValueError, match=match):
        _clf(_bundle(render=render), FakeRuntime())


@pytest.mark.unit
def test_empty_query_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        _clf(_bundle(), FakeRuntime()).classify("")


@pytest.mark.unit
def test_soft_version_needs_its_patched_runtime():
    bundle = _bundle()
    patch = VocabTokenPatch(
        tuple(bundle.soft_token_ids), bundle.prompt, tuple(bundle.label_token_ids),
        bundle.head_weight,
    )
    with pytest.raises(ValueError, match="does not hold its vocabulary rows"):
        PromptClassifier(bundle, FakeRuntime(), vocab_patch=patch)  # unpatched runtime


@pytest.mark.unit
def test_soft_version_without_token_ids_is_rejected():
    bundle = _bundle()
    meta = {k: v for k, v in bundle.meta.items() if k not in ("soft_token_ids", "label_token_ids")}
    bare = ClassifierBundle("soft", bundle.prompt, bundle.head_weight, bundle.head_bias,
                            bundle.fp_hidden, meta)
    with pytest.raises(ValueError, match="token form only"):
        PromptClassifier(bare, FakeRuntime())


@pytest.mark.unit
def test_only_hard_versions_rebind_to_another_runtime():
    hard = PromptClassifier(_bundle(kind="hard", n_classes=2, class_semantics=["E", "H"]),
                            FakeRuntime())
    other = FakeRuntime()
    hard.rebind_runtime(other)
    hard.classify("abcd")
    assert len(other.calls) == 1
    with pytest.raises(ValueError, match="patched runtime"):
        _clf(_bundle(), FakeRuntime()).rebind_runtime(other)


@pytest.mark.unit
def test_decision_helpers():
    cases = (
        ([0.2, 0.7, 0.1], 0.7, 1),  # at the threshold: decided
        ([0.2, 0.69, 0.11], 0.7, None),
        ([0.4, 0.35, 0.25], 0.0, 0),
        ([0.5, 0.5], 0.5, 0),  # tie: the first zone
        ([0.1, 0.9], 0.5, 1),
    )
    for probs, threshold, expected in cases:
        assert decide(probs, threshold) == expected
    p = np.full(12, 1 / 12)
    p[11] += 0.1
    p[0] -= 0.1
    merged = zone_probs(p, [1] * 6 + [0] * 6)  # classes 6-11 local (zone 0)
    assert merged.tolist() == pytest.approx([0.6, 0.4])
    assert zone_probs([0.2, 0.8]).tolist() == [0.2, 0.8]  # no class_zones: one zone per class
    for p_e, expected in (
        (0.29, 1), (0.3, 1), (0.31, -1), (0.5, -1), (0.69, -1), (0.7, 0), (0.71, 0)
    ):
        result = hard_result({"E": p_e, "H": 1 - p_e}, settings.HARD_THRESHOLD)
        assert (-1 if result.index is None else result.index) == expected
    result = hard_result(
        {"local": 0.1, "cloud": 0.15, "planning": 0.75}, 0.7, raw={"local": 0.2}
    )
    assert (result.label, result.index, result.confidence, result.kind) == (
        "planning", 2, 0.75, "hard",
    )
    assert result.raw == {"label_logits": {"local": 0.2}}


@pytest.mark.unit
def test_two_zones_abstain_symmetrically_around_one_half():
    """Two zones: max(p, 1-p) >= t  <=>  |p - 0.5| >= t - 0.5 (the former E/H rule)."""
    rng = np.random.default_rng(0)
    for threshold in (0.51, 0.6, 0.7, 0.9):
        probabilities = np.concatenate(
            [rng.uniform(size=1_000), [threshold, 1 - threshold, 0.5]]
        )
        margin = threshold - 0.5
        for probability in probabilities:
            former = (
                None
                if abs(probability - 0.5) < margin
                else (0 if probability > 0.5 else 1)
            )
            actual = decide([probability, 1 - probability], threshold)
            on_boundary = abs(abs(probability - 0.5) - margin) <= 1e-12
            assert actual == former or on_boundary

def _offline_classifier(e_logit: float, threshold: float = 0.7) -> OVQwenClassifier:
    clf = OVQwenClassifier.__new__(OVQwenClassifier)  # skip __init__: no backbone runtime
    clf.labels, clf.system_prompt, clf.cache_size = ["E", "H"], "", 8
    clf.threshold = threshold
    clf._cache = OrderedDict()
    clf.forward_calls = 0
    # _render reads the backbone's chat style; the offline stand-in is Qwen
    clf._shared_runtime = False
    clf._runtime = SimpleNamespace(chat_style="qwen")

    def label_logits(_prompt):
        clf.forward_calls += 1
        return np.array([e_logit, 0.0])

    clf._label_logits = label_logits
    return clf


@pytest.mark.unit
def test_changing_threshold_applies_on_cache_hit():
    clf = _offline_classifier(e_logit=1.0)  # p(E) ~= 0.73
    assert clf.classify("q").index == 0
    clf.threshold = 0.8
    result = clf.classify("q")
    # Served from cache, decided with the new threshold.
    assert result.index is None and clf.forward_calls == 1


@pytest.mark.unit
def test_labels_are_validated_before_loading():
    cases = (
        ({"labels": ["local", "cloud"], "label_tokens": ["A"]}, "one token per label"),
        ({"labels": ["E", "E"]}, "distinct"),
        ({"labels": ["E"]}, "at least two"),
    )
    for kwargs, match in cases:
        with pytest.raises(ValueError, match=match):
            OVQwenClassifier(ov_model="/nonexistent", **kwargs)


@pytest.mark.unit
def test_known_backbones_default_and_env_names():
    assert settings.KNOWN_BACKBONES["qwen35-2b"] == "Qwen/Qwen3.5-2B"
    assert settings.KNOWN_BACKBONES["qwen3-0.6b"] == "Qwen/Qwen3-0.6B"
    assert settings.default_backbone({}) == "qwen35-2b"
    assert settings.default_backbone({"IR_BACKBONE": "qwen3-0.6b"}) == "qwen3-0.6b"
    assert settings.ov_model_env_var("qwen35-2b") == "IR_OV_MODEL_QWEN35_2B"
    assert settings.ov_model_env_var("qwen3-0.6b") == "IR_OV_MODEL_QWEN3_0P6B"
    with pytest.raises(ConfigurationError, match="IR_BACKBONE"):
        settings.default_backbone({"IR_BACKBONE": "llama"})


@pytest.mark.unit
def test_resolve_ov_model_path(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    # IR_OV_MODEL is the default backbone's path ...
    assert settings.resolve_ov_model_path(env={"IR_OV_MODEL": str(a)}) == str(a)
    # ... the per-backbone variable wins ...
    env = {"IR_OV_MODEL": str(a), "IR_OV_MODEL_QWEN35_2B": str(b)}
    assert settings.resolve_ov_model_path(env=env) == str(b)
    # ... and IR_OV_MODEL never stands in for a non-default backbone.
    with pytest.raises(ConfigurationError, match="IR_OV_MODEL_QWEN3_0P6B"):
        settings.resolve_ov_model_path("qwen3-0.6b", env={"IR_OV_MODEL": str(a)})
    assert settings.resolve_ov_model_path("qwen3-0.6b", env={"IR_OV_MODEL_QWEN3_0P6B": str(b)}) == str(b)
    with pytest.raises(ConfigurationError, match="Set IR_OV_MODEL"):
        settings.resolve_ov_model_path(env={})
    with pytest.raises(ConfigurationError, match="missing directory"):
        settings.resolve_ov_model_path(env={"IR_OV_MODEL": str(tmp_path / "nope")})
    with pytest.raises(ConfigurationError, match="Unknown backbone"):
        settings.resolve_ov_model_path("llama", env={})


@pytest.mark.unit
def test_multiclass_config_appends_the_answer_key():
    cfg = settings.multiclass_classifier_config(
        "/models/x", ["local", "cloud", "planning"], "Pick a category.\n", threshold=0.6
    )
    assert cfg.labels == ["local", "cloud", "planning"] and cfg.label_tokens == ["A", "B", "C"]
    assert cfg.system_prompt.startswith("Pick a category.\n\n")
    assert cfg.system_prompt.endswith("A: local\nB: cloud\nC: planning")
    assert cfg.threshold == 0.6
    # The default floor for text-prompt classifiers.
    assert settings.multiclass_classifier_config("/m", ["a", "b"], "p").threshold == 0.7
    with pytest.raises(ConfigurationError, match="2-26 labels"):
        settings.multiclass_classifier_config("/models/x", [f"c{i}" for i in range(27)], "p")
