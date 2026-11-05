# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the L1/L2/L3 backbone compatibility checks.

A fake runtime stands in for the OpenVINO backbone: ``encode`` maps text to
fixed ids, ``last_hidden`` returns a controlled vector (so fingerprint cosines
are computable in the test), ``label_rows`` returns controlled head rows.
"""
import json
import numpy as np
import pytest
from src.rsd.model_based.bundle import ClassifierBundle
from src.rsd.model_based.settings import FINGERPRINT_MIN_COS, fingerprint_min_cos
from src.rsd.model_based.validate import VersionValidationError, validate_against_runtime
H = 8
PROBES = ['p1', 'p2', 'p3', 'p4']
MODEL_NAME = 'Qwen/Qwen3.5-2B'
HIDDEN_ROW = np.full(H, 0.5)

class FakeRuntime:
    """Deterministic backbone: fixed ids, fixed hidden, controlled label rows."""

    def __init__(self, hidden_row=None, label_rows_matrix=None):
        self.hidden_row = hidden_row if hidden_row is not None else np.full(H, 0.5, dtype=np.float64)
        self.label_rows_matrix = label_rows_matrix
        self.fingerprint_forwards = 0

    chat_style = "qwen"  # hard prompts render in the Qwen template

    def strip_prompt_prefix(self, ids):
        return np.asarray(ids, dtype=np.int64)  # no tokenizer-level prefix

    def encode(self, text):
        single = {'E': 7, 'H': 9, 'A': 20, 'B': 21, 'C': 22}
        if text in single:
            return np.array([single[text]])
        return np.array([10, 11])

    def embed(self, ids):
        return np.ones((1, len(ids), H), dtype=np.float32)

    def last_hidden(self, embeds, attention_mask=None):
        self.fingerprint_forwards += 1
        return self.hidden_row.copy()

    def label_rows(self, ids):
        if self.label_rows_matrix is not None:
            return self.label_rows_matrix
        return np.stack([self.hidden_row for _ in ids])

def _soft_bundle(model_name=MODEL_NAME, fp_hidden=None, fp_token_ids=(10, 11)):
    meta = {'model_name': model_name, 'version': 'v1', 'hidden': H, 'num_classes': 2, 'threshold': 0.5, 'fp_probes': json.dumps(PROBES), 'fp_token_ids': list(fp_token_ids), 'fp_ref': 'test', 'class_semantics': json.dumps(['cloud', 'local']), 'class_zones': [1, 0], 'zone_names': json.dumps(['cloud', 'local'])}
    fp = fp_hidden if fp_hidden is not None else np.stack([HIDDEN_ROW for _ in PROBES])
    return ClassifierBundle(kind='soft', prompt=np.zeros((4, H)), head_weight=np.zeros((2, H)), head_bias=np.zeros(2), fp_hidden=fp, meta=meta)

def _hard_bundle(model_name=MODEL_NAME, head_weight=None, label_token_ids=(7, 9), label_tokens=('E', 'H'), class_semantics=('E', 'H')):
    n = len(label_tokens)
    meta = {'model_name': model_name, 'version': 'v3', 'hidden': H, 'num_classes': n, 'threshold': 0.7, 'fp_probes': json.dumps(PROBES), 'fp_token_ids': [10, 11], 'fp_ref': 'test', 'class_semantics': json.dumps(list(class_semantics)), 'label_tokens': json.dumps(list(label_tokens)), 'label_token_ids': list(label_token_ids)}
    fp = np.stack([HIDDEN_ROW for _ in PROBES])
    rows = np.stack([HIDDEN_ROW] * n) if head_weight is None else head_weight
    return ClassifierBundle(kind='hard', prompt='system prompt', head_weight=rows, head_bias=np.zeros(n), fp_hidden=fp, meta=meta)

def _runtime(label_rows_matrix=None):
    rt = FakeRuntime()
    if label_rows_matrix is not None:
        rt.label_rows_matrix = label_rows_matrix
    return rt

@pytest.mark.unit
def test_soft_version_passes_all_levels():
    report = validate_against_runtime(_soft_bundle(), _runtime())
    assert report['L1'] == 'ok'
    assert report['L2'] == 'ok'
    assert report['L3_min_cos'] == pytest.approx(1.0)
    assert report['backbone'] == 'qwen35-2b'
    assert 'hard_head_min_cos' not in report

@pytest.mark.unit
def test_hard_version_passes_with_head_row_check():
    runtime = _runtime(label_rows_matrix=np.stack([HIDDEN_ROW, HIDDEN_ROW]))
    report = validate_against_runtime(_hard_bundle(), runtime)
    assert report['L1'] == 'ok'
    assert report['L2'] == 'ok'
    assert report['L3_min_cos'] == pytest.approx(1.0)
    assert report['hard_head_min_cos'] == pytest.approx(1.0)

@pytest.mark.unit
def test_l1_unknown_model_name_rejected():
    bundle = _soft_bundle(model_name='Qwen/Not-A-Known-Backbone')
    with pytest.raises(VersionValidationError, match='L1'):
        validate_against_runtime(bundle, _runtime())

@pytest.mark.unit
def test_l1_backbone_key_mismatch_rejected():
    bundle = _soft_bundle(model_name='Qwen/Qwen3.5-2B')
    with pytest.raises(VersionValidationError, match='does not match backbone'):
        validate_against_runtime(bundle, _runtime(), backbone='qwen3-0.6b')

@pytest.mark.unit
def test_l2_packed_token_ids_mismatch_rejected():
    bundle = _soft_bundle(fp_token_ids=[99, 100])
    with pytest.raises(VersionValidationError, match='L2'):
        validate_against_runtime(bundle, _runtime())

@pytest.mark.unit
def test_multiclass_hard_checks_the_answer_codes_not_the_class_names():
    bundle = _hard_bundle(label_tokens=('A', 'B', 'C'), label_token_ids=(20, 21, 22), class_semantics=('local', 'cloud', 'planning'))
    report = validate_against_runtime(bundle, _runtime())
    assert report['L2'] == 'ok'

@pytest.mark.unit
def test_l2_rejects_an_answer_code_that_is_not_one_token():
    bundle = _hard_bundle(label_tokens=('E', 'HH'), label_token_ids=(7, 9))
    with pytest.raises(VersionValidationError, match='exactly one token'):
        validate_against_runtime(bundle, _runtime())

@pytest.mark.unit
def test_l2_hard_label_mismatch_rejected_before_fingerprint():
    runtime = _runtime()
    with pytest.raises(VersionValidationError, match='label tokens'):
        validate_against_runtime(_hard_bundle(label_token_ids=(8, 9)), runtime)
    assert runtime.fingerprint_forwards == 0

@pytest.mark.unit
def test_l3_tampered_fingerprint_rejected():
    rng = np.random.default_rng(3)
    fp = rng.standard_normal((len(PROBES), H)).astype(np.float32)
    bundle = _soft_bundle(fp_hidden=fp)
    with pytest.raises(VersionValidationError, match='fingerprint min cos'):
        validate_against_runtime(bundle, _runtime(), fp_min_cos=0.98)

@pytest.mark.unit
def test_l3_zero_fingerprint_rejected():
    bundle = _soft_bundle(fp_hidden=np.zeros((len(PROBES), H)))
    with pytest.raises(VersionValidationError, match='fingerprint min cos'):
        validate_against_runtime(bundle, _runtime(), fp_min_cos=0.98)

@pytest.mark.unit
def test_l3_relaxed_threshold_allows_drifted_fingerprint():
    drifted = np.zeros((len(PROBES), H), dtype=np.float64)
    drifted[:, 0] = 1.0
    bundle = _soft_bundle(fp_hidden=drifted)
    with pytest.raises(VersionValidationError, match='fingerprint min cos'):
        validate_against_runtime(bundle, _runtime(), fp_min_cos=0.98)
    report = validate_against_runtime(bundle, _runtime(), fp_min_cos=0.3)
    assert report['L3_min_cos'] < 0.98

@pytest.mark.unit
def test_l3_hard_head_rows_mismatch_rejected():
    other = np.full((2, H), -1.0)
    runtime = _runtime(label_rows_matrix=other)
    bundle = _hard_bundle(head_weight=np.full((2, H), 1.0))
    with pytest.raises(VersionValidationError, match='hard head rows'):
        validate_against_runtime(bundle, runtime)

@pytest.mark.unit
def test_validation_failure_names_the_level():
    bundle = _soft_bundle(fp_token_ids=[1])
    try:
        validate_against_runtime(bundle, _runtime(), fp_min_cos=0.98)
    except VersionValidationError as exc:
        assert exc.level == 'L2'
    else:
        pytest.fail('expected an L2 failure')

@pytest.mark.unit
def test_invalid_fingerprint_threshold_falls_back():
    for value in ('nan', 'inf', '-0.1', '1.1', 'invalid'):
        assert fingerprint_min_cos({'IR_FP_MIN_COS': value}) == FINGERPRINT_MIN_COS
