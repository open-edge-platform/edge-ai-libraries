# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Token-form bundle, classifier, vocabulary-layout, and row-check contracts."""

from __future__ import annotations

import numpy as np
import pytest

from src.rsd.model_based import vocab_tokens as vt
from src.rsd.model_based.bundle import KIND_SOFT, ClassifierBundle
from src.rsd.model_based.classifier import PromptClassifier
from src.rsd.model_based.format import RcvFormatError, encode_rcv
from src.rsd.model_based.validate import VersionValidationError, check_vocab_rows

H, K, C = 8, 3, 4
SOFT_IDS = list(range(248077, 248080))
LABEL_IDS = list(range(248080, 248084))
PAD_ID = 30


class FakeVocabRuntime:
    hidden_size = H

    def __init__(self, table, digest="patched"):
        self.table = table
        self.token_patch_digest = digest
        self.embed_ids = []
        self.logits_calls = []

    def encode(self, text):
        return np.array([ord(ch) % 29 for ch in text], dtype=np.int64)

    def embed(self, ids):
        self.embed_ids.append(np.asarray(ids, dtype=np.int64).copy())
        return self.table[np.asarray(ids)][None]

    def class_logits(self, embeds, attention_mask=None):
        self.logits_calls.append((embeds, attention_mask))
        hidden = embeds[0, -1].astype(np.float64)
        return (hidden @ self.table[LABEL_IDS].astype(np.float64).T).astype(np.float32)

    def label_rows(self, ids):
        return self.table[np.asarray(ids)]


def _bundle(seed=3, token_form=True, **meta_overrides) -> ClassifierBundle:
    rng = np.random.default_rng(seed)
    meta = {
        "model_name": "Qwen/Qwen3.5-2B",
        "version": "v1",
        "created": "2026-10-26T00:00:00Z",
        "hidden": H,
        "fp_probes": ["probe"],
        "fp_ref": "hf-fp32",
        "fp_token_ids": [1, 2],
        "num_classes": C,
        "class_labels": list(range(C)),
        "class_semantics": [f"c{i}" for i in range(C)],
        "class_zones": [1, 1, 0, 0],
        "zone_names": ["local", "cloud"],
        "threshold": 0.5,
        "text_max_tokens": 2040,
        "truncation_side": "left",
        "render": {
            "template": "raw",
            "soft_position": "before",
            "padding": {"between_soft_and_query": 2, "pad_token_id": PAD_ID},
        },
    }
    if token_form:
        meta.update(soft_token_ids=SOFT_IDS, label_token_ids=LABEL_IDS)
    meta.update(meta_overrides)
    return ClassifierBundle(
        kind=KIND_SOFT,
        prompt=rng.standard_normal((K, H)).astype(np.float32),
        head_weight=rng.standard_normal((C, H)).astype(np.float32),
        head_bias=rng.standard_normal(C).astype(np.float32),
        fp_hidden=rng.standard_normal((1, H)).astype(np.float32),
        meta=meta,
    )


def _copy_with_meta(bundle, meta):
    return ClassifierBundle(
        bundle.kind,
        bundle.prompt,
        bundle.head_weight,
        bundle.head_bias,
        bundle.fp_hidden,
        meta,
    )


def _runtime_for(bundle) -> FakeVocabRuntime:
    table = np.random.default_rng(4).standard_normal((248320, H)).astype(np.float32)
    table[SOFT_IDS] = bundle.prompt
    table[LABEL_IDS] = bundle.head_weight
    return FakeVocabRuntime(table, digest=vt.token_patch(bundle).digest)


@pytest.mark.unit
def test_token_form_format_contract():
    bundle = _bundle()
    for key in ("soft_token_ids", "label_token_ids"):
        meta = dict(bundle.meta)
        meta.pop(key)
        with pytest.raises(RcvFormatError, match="needs soft_token_ids and label_token_ids"):
            encode_rcv(_copy_with_meta(bundle, meta))

    for overrides, match in (
        ({"soft_token_ids": [1, 2]}, "soft_token_ids must have k=3"),
        ({"soft_token_ids": [5, 5, 6]}, "must not repeat"),
    ):
        with pytest.raises(RcvFormatError, match=match):
            encode_rcv(_bundle(**overrides))

@pytest.mark.unit
def test_token_form_classifier_and_runtime_validation():
    bundle = _bundle()
    runtime = _runtime_for(bundle)
    classifier = PromptClassifier(bundle, runtime, cache_size=0)
    classifier.classify("abcd")

    query_ids = [ord(ch) % 29 for ch in "abcd"]
    assert runtime.embed_ids[0].tolist() == SOFT_IDS + [PAD_ID, PAD_ID] + query_ids
    embeds, mask = runtime.logits_calls[0]
    np.testing.assert_array_equal(mask, [1] * K + [0, 0] + [1] * len(query_ids))
    logits = runtime.table[LABEL_IDS].astype(np.float64) @ embeds[0, -1] + bundle.head_bias
    expected = np.exp(logits - logits.max())
    np.testing.assert_allclose(
        classifier.class_probs("abcd"), expected / expected.sum(), rtol=1e-6
    )

    assert check_vocab_rows(bundle, runtime) < 1e-6
    wrong = _runtime_for(bundle)
    wrong.table[LABEL_IDS[0]] += 1
    with pytest.raises(VersionValidationError, match="the lm_head rows"):
        check_vocab_rows(bundle, wrong)


@pytest.mark.unit
def test_vocabulary_layout_and_token_strings():
    expected = {
        "qwen35-2b": (248077, 248085),
        "qwen3-0.6b": (151669, 151677),
    }
    for backbone, (first, first_class) in expected.items():
        assert vt.soft_token_ids(backbone, 8) == list(range(first, first + 8))
        assert vt.class_token_ids(backbone, 8, 12) == list(range(first_class, first_class + 12))
    with pytest.raises(ValueError, match="no vocabulary-token layout"):
        vt.layout_for_backbone("llama")
    with pytest.raises(ValueError, match="do not fit"):
        vt.class_token_ids("qwen35-2b", 200, 100)


@pytest.mark.unit
def test_token_id_generation_and_validation():
    assembled = _bundle(token_form=False)
    token_form = vt.add_token_ids(assembled)
    patch = vt.token_patch(token_form)
    assert (patch.soft_ids, patch.label_ids) == (tuple(SOFT_IDS), tuple(LABEL_IDS))
    assert vt.add_token_ids(token_form) is token_form
    assert vt.token_patch(vt.add_token_ids(_bundle(seed=1, token_form=False))).digest != (
        patch.digest
    )
    vt.check_token_ids(token_form)
    shifted = {
        "soft_token_ids": list(range(248078, 248078 + K)),
        "label_token_ids": list(range(248078 + K, 248078 + K + C)),
    }
    with pytest.raises(ValueError, match="do not follow"):
        vt.check_token_ids(_bundle(**shifted))
