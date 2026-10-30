# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The shipped default versions (token form) compute the soft prompt's math.

The reference is the math the soft prompts were trained with, computed here
outside the router: an unpatched backbone fed the soft vectors as
``inputs_embeds``, then ``head @ hidden + bias``. The token-form classifier
(rows written into the vocabulary, class logits read from the full lm_head)
must match it up to the f16/bf16 rounding of the written rows.

Runs per backbone when its IR is configured (``IR_OV_MODEL`` /
``IR_OV_MODEL_QWEN35_2B`` for qwen35-2b, ``IR_OV_MODEL_QWEN3_0P6B`` for
qwen3-0.6b); the IR must be the original vocab-logits export (FP16/BF16 --
weight-compressed IRs cannot host token-form versions and are rejected).
With ``IR_EVAL_DATA`` pointing at a ``binary/test.jsonl``-style file (rows
with ``prompt`` and ``route``), also reports route accuracy against the
recorded baselines (2B 80.37% / 0.6B 74.50%, measured 2026-10-26).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from src.exceptions import ConfigurationError
from src.rsd.model_based import settings
from src.rsd.model_based.format import read_rcv
from src.rsd.model_based.vocab_tokens import token_patch

pytestmark = pytest.mark.slow

BASELINE_ACCURACY = {"qwen35-2b": 0.8037, "qwen3-0.6b": 0.7450}


def _ir_dir(backbone: str) -> str:
    try:
        return settings.resolve_ov_model_path(backbone)
    except ConfigurationError:
        pytest.skip(f"no IR configured for {backbone} ({settings.ov_model_env_var(backbone)})")


def _eval_rows() -> list[dict]:
    path = settings.os.environ.get("IR_EVAL_DATA")
    if not path or not Path(path).is_file():
        pytest.skip("no eval data configured (IR_EVAL_DATA)")
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line
    ]


@pytest.mark.parametrize("backbone", sorted(settings.KNOWN_BACKBONES))
def test_token_form_default_matches_the_soft_prompt_math(backbone):
    """Same queries: differences only from f16/bf16 rounding of the written rows."""
    ir_dir = _ir_dir(backbone)
    from src.rsd.model_based.classifier import PromptClassifier
    from src.rsd.model_based.runtime import BackboneRuntime
    from src.rsd.model_based.validate import validate_against_runtime

    packaged = settings.default_version_path(backbone)  # token form (v1, repacked)
    bundle = read_rcv(packaged)
    assert bundle.token_form, "the shipped default should be token form"
    patch = token_patch(bundle)

    t0 = time.perf_counter()
    rt_token = BackboneRuntime(ir_dir, "CPU", token_patch=patch)
    load_s = time.perf_counter() - t0
    rt_plain = BackboneRuntime(ir_dir, "CPU")

    report = validate_against_runtime(bundle, rt_token, backbone=backbone)
    assert report["L1"] == "ok" and report["L2"] == "ok"
    assert report["L3_min_cos"] >= 0.98
    # the rows written into the graph read back as the packed data
    assert report["vocab_rows_max_diff"] < 0.02

    clf_token = PromptClassifier(bundle, rt_token, cache_size=0)
    pad_ids = np.full(
        bundle.meta["render"]["padding"]["between_soft_and_query"],
        bundle.meta["render"]["padding"]["pad_token_id"],
        dtype=np.int64,
    )

    def reference_probs(query):
        ids = rt_plain.encode(query)
        soft = bundle.prompt[None].astype(np.float32)
        embeds = np.concatenate([soft, rt_plain.embed(np.concatenate([pad_ids, ids]))], axis=1)
        mask = np.concatenate(
            [np.ones(len(bundle.prompt)), np.zeros(len(pad_ids)), np.ones(len(ids))]
        ).astype(np.int64)
        hidden = rt_plain.last_hidden(embeds, mask).astype(np.float64)
        logits = bundle.head_weight.astype(np.float64) @ hidden + bundle.head_bias
        e = np.exp(logits - logits.max())
        return e / e.sum()

    queries = [
        "What is the capital of France?",
        "用一句话解释什么是光合作用。",
        "Write a Python function that merges two sorted lists and explain its time complexity.",
        "请比较 Raft 和 Paxos 在成员变更、日志压缩和读一致性上的差异。",
    ]
    for query in queries:
        token = float(clf_token.class_probs(query)[:6].sum())  # cloud zone
        reference = float(reference_probs(query)[:6].sum())
        assert abs(token - reference) < 1e-2, f"{query!r}: {token} vs {reference}"
    print(f"\n{backbone}: token-form load {load_s:.1f}s, "
          f"vocab_rows_max_diff={report['vocab_rows_max_diff']:.5f}")


@pytest.mark.parametrize("backbone", sorted(settings.KNOWN_BACKBONES))
def test_token_form_default_route_accuracy(backbone):
    """Route accuracy on the binary eval set stays at the recorded level."""
    ir_dir = _ir_dir(backbone)
    rows = _eval_rows()
    from src.rsd.model_based.classifier import PromptClassifier
    from src.rsd.model_based.runtime import BackboneRuntime

    bundle = read_rcv(settings.default_version_path(backbone))
    clf = PromptClassifier(
        bundle, BackboneRuntime(ir_dir, "CPU", token_patch=token_patch(bundle)), cache_size=0
    )

    correct = 0
    for row in rows:
        result = clf.classify(row["prompt"])
        predicted = bundle.zone_names[result.index]  # "local" / "cloud"
        correct += predicted == row["route"]
    accuracy = correct / len(rows)
    baseline = BASELINE_ACCURACY[backbone]
    print(
        f"\n{backbone}: token form {accuracy:.4f} over {len(rows)} rows (baseline {baseline:.4f})"
    )
    assert accuracy >= baseline - 0.01  # rounding-only differences
