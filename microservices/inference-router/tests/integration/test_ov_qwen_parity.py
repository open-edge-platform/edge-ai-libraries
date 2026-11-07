# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Raw-OpenVINO hard-prompt classifier tests against a real IR.

The classifier under test is the multi-class one a ``ModelBasedRule`` with a
``prompt_file`` builds: the shipped ``prompts/multiclass.example.txt`` plus the
appended answer key, labels ``local`` / ``cloud`` / ``planning``.

* **Contract tests** hold for any backbone / prompt: the IR loads, results are
  well-formed, the decision is consistent with the scores, and classification
  is deterministic and cache-consistent.
* **Head equivalence**: the C-row head (``last_hidden @ label_rows.T``) must
  reproduce the label-code entries of the IR's own full-vocab logits, and the
  decision must not change. Checked on IRs with uncompressed (original) weights
  only; weight-compressed IRs (INT8 / INT4) are skipped because deployment
  precision is validated separately.

Runs only when a real IR is available:

    IR_OV_MODEL=/path/to/hf-Qwen3.5-2B-fp16-ov pytest -m slow \
        tests/integration/test_ov_qwen_parity.py

The directory is any layout :mod:`src.rsd.model_based.runtime` accepts: a split
VLM IR (``openvino_text_embeddings_model.xml`` + ``openvino_language_model.xml``)
or a single-graph ``openvino_model.xml``, plus ``openvino_tokenizer.xml``.
Skipped otherwise so CI without the model (or without OpenVINO) stays green.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

_MODEL = os.environ.get("IR_OV_MODEL")
_SPLIT_IR = ("openvino_text_embeddings_model.xml", "openvino_language_model.xml")
_SINGLE_IR = ("openvino_model.xml",)


def _model_ready() -> bool:
    if not _MODEL:
        return False
    root = Path(_MODEL).expanduser()
    if not (root / "openvino_tokenizer.xml").exists():
        return False
    return any(all((root / name).exists() for name in layout) for layout in (_SPLIT_IR, _SINGLE_IR))


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not _model_ready(),
        reason="set IR_OV_MODEL to a Qwen OpenVINO IR dir to run raw-OV parity",
    ),
]


_LABELS = ["local", "cloud", "planning"]


def _classifier_config(threshold=None):
    from src.rsd.model_based.settings import multiclass_classifier_config

    prompt = (
        Path(__file__).resolve().parents[2] / "src/rsd/model_based/prompts/multiclass.example.txt"
    ).read_text(encoding="utf-8")
    prompt = prompt.split("NOTE:")[0]  # the template's notes to operators are not prompt text
    kwargs = {} if threshold is None else {"threshold": threshold}
    cfg = multiclass_classifier_config(str(Path(_MODEL).expanduser()), _LABELS, prompt, **kwargs)
    cfg.device = "CPU"  # set on the config, not via os.environ, so nothing leaks to other tests
    return cfg


@pytest.fixture(scope="module")
def classifier():
    """Build the multi-class classifier on CPU against the mounted IR."""
    from src.rsd.model_based.settings import build_classifier

    return build_classifier(_classifier_config())


# ---------------------------------------------------------------------------
# Contract: holds for any backbone / prompt combination
# ---------------------------------------------------------------------------

_CONTRACT_INPUTS = [
    "What is 2 + 2?",
    "用一句话解释什么是光合作用。",
    "帮我 fix 这个 Python bug：list index out of range",
    "Polish this paragraph for clarity.",
    "Break our monolith-to-microservices migration into phases with milestones "
    "and dependencies.",
    "🙂",
    "",
]


def _assert_well_formed(classifier, result):
    from src.rsd.model_based.base import decide

    assert list(result.scores) == classifier.labels
    assert all(0.0 <= p <= 1.0 for p in result.scores.values())
    assert math.isclose(sum(result.scores.values()), 1.0, abs_tol=1e-6)
    # The decision is the hard one: most likely class unless below the result's own threshold.
    assert result.index == decide(list(result.scores.values()), result.threshold)
    assert result.label == (None if result.index is None else classifier.labels[result.index])
    assert result.confidence == max(result.scores.values())


@pytest.mark.parametrize("query", _CONTRACT_INPUTS)
def test_result_is_well_formed(classifier, query):
    assert classifier.label_tokens == ["A", "B", "C"]
    _assert_well_formed(classifier, classifier.classify(query))


def test_classify_is_deterministic_and_cached(classifier):
    first = classifier.classify("Explain the difference between TCP and UDP.")
    second = classifier.classify("Explain the difference between TCP and UDP.")  # cache hit
    assert (first.index, first.scores) == (second.index, second.scores)

    classifier._cache.clear()
    recomputed = classifier.classify("Explain the difference between TCP and UDP.")  # cache miss
    assert recomputed.label == first.label
    for label, p in first.scores.items():
        assert recomputed.scores[label] == pytest.approx(p, abs=1e-6)


# ---------------------------------------------------------------------------
# Backbone runtime: C-row head == the IR's own lm_head, runtime compiled once
# ---------------------------------------------------------------------------

_EQUIVALENCE_INPUTS = [
    *_CONTRACT_INPUTS,
    "Write a haiku about spring.",
    "Design a distributed consensus protocol tolerant to Byzantine faults and prove its safety.",
    "Summarise this paragraph in one sentence: "
    + "The quick brown fox jumps over the lazy dog. " * 40,
    "请比较 Raft 和 Paxos 在成员变更、日志压缩和读一致性上的差异，并给出工程实现上的取舍。",
]


def _lm_head_compressed(model) -> bool:
    """True when the lm_head weight is stored in an integer (compressed) type."""
    stack = [model.get_results()[0].input_value(0).get_node().input_value(1).get_node()]
    while stack:
        node = stack.pop()
        if node.get_type_name() == "Constant" and node.get_output_element_type(0).is_integral():
            return True
        stack.extend(value.get_node() for value in node.input_values())
    return False


@pytest.fixture(scope="module")
def vocab_logits():
    """The pre-runtime path: run the IR as exported and read its full-vocab logits.

    Returns ``fn(prompt) -> logits[vocab]`` at the last position, or skips when
    the IR no longer outputs logits (router-contract export).
    """
    import numpy as np
    import openvino as ov
    import openvino_tokenizers  # noqa: F401

    root = Path(_MODEL).expanduser()
    core = ov.Core()
    tok = core.compile_model(str(root / "openvino_tokenizer.xml"), "CPU")
    ids_port = next(o for o in tok.outputs if "input_ids" in o.get_names())
    split = (root / "openvino_language_model.xml").exists()
    lm_xml = "openvino_language_model.xml" if split else "openvino_model.xml"
    lm = core.read_model(str(root / lm_xml))
    if not any("logits" in o.get_names() for o in lm.outputs):
        pytest.skip("IR outputs last_hidden_state only; no vocab logits to compare against")
    if _lm_head_compressed(lm):
        pytest.skip(
            "weight-compressed IR: equivalence is checked on original weights only"
        )
    pos_rank = lm.input("position_ids").get_partial_shape().rank.get_length()
    lm = core.compile_model(lm, "CPU")
    te = None
    if split:
        te = core.compile_model(str(root / "openvino_text_embeddings_model.xml"), "CPU")

    def run(prompt: str):
        ids = tok([prompt])[ids_port].astype(np.int64)
        seq_len = ids.shape[1]
        positions = np.arange(seq_len, dtype=np.int64)[None]
        feed = {
            "attention_mask": np.ones((1, seq_len), dtype=np.int64),
            "position_ids": np.tile(positions[None], (4, 1, 1)) if pos_rank == 3 else positions,
            "beam_idx": np.zeros((1,), dtype=np.int32),
        }
        if split:
            feed["inputs_embeds"] = te(ids)[te.output(0)]
        else:
            feed["input_ids"] = ids
        req = lm.create_infer_request()
        req.reset_state()
        return req.infer(feed)[lm.output("logits")][0, -1].astype(np.float64)

    return run


@pytest.mark.parametrize("query", _EQUIVALENCE_INPUTS)
def test_label_head_matches_vocab_logits(classifier, vocab_logits, query):
    from src.rsd.model_based.classifier import hard_result, label_scores

    logits = vocab_logits(classifier._render(query))
    old = [logits[classifier._label_ids[c]] for c in classifier.label_tokens]
    old_result = hard_result(label_scores(old, classifier.labels), classifier.threshold)

    classifier._cache.clear()
    result = classifier.classify(query)
    for label, logit in zip(classifier.labels, old):
        assert result.raw["label_logits"][label] == pytest.approx(logit, abs=1e-2)
    assert result.index == old_result.index


def test_classifiers_on_one_backbone_share_the_runtime(classifier):
    from src.rsd.model_based.settings import build_classifier

    other = build_classifier(_classifier_config(threshold=0.9))  # same backbone x device
    assert other is not classifier
    assert other._runtime is classifier._runtime  # not recompiled


def test_tokenizer_alone_matches_the_runtime(classifier):
    from src.rsd.model_based.runtime import Tokenizer

    tokenizer = Tokenizer(str(Path(_MODEL).expanduser()))  # no backbone compiled
    for query in _CONTRACT_INPUTS:
        assert tokenizer.encode(query).tolist() == classifier._runtime.encode(query).tolist()
