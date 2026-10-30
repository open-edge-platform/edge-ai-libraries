# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Hard classifier/runtime-cache tests without a real OpenVINO runtime."""
from __future__ import annotations

import gc
import json
import weakref
from types import SimpleNamespace
from weakref import WeakValueDictionary

import numpy as np
import pytest

from src.rsd.model_based import runtime as rt_mod
from src.rsd.model_based.classifier import OVQwenClassifier, label_scores

HIDDEN, V = 4, 10
TOKENS = {"E": 7, "H": 9}
XIN = np.random.default_rng(0).normal(size=(1, 5, HIDDEN)).astype(np.float32)
W = np.arange(V * HIDDEN, dtype=np.float32).reshape(V, HIDDEN) % 7


class FakeRuntime:
    """Encode chars as token IDs and return a fixed hidden state."""

    def __init__(self, hidden=None, device="CPU"):
        self.device = device
        self.hidden = np.asarray(hidden if hidden is not None else [1.0, -2.0, 0.5, 3.0], dtype=np.float32)
        self.table = np.random.default_rng(0).normal(size=(32, HIDDEN)).astype(np.float32)
        self.prompts, self.label_row_calls = [], []

    chat_style = "qwen"  # hard prompts render in the Qwen template

    def strip_prompt_prefix(self, ids):
        return np.asarray(ids, dtype=np.int64)  # no tokenizer-level prefix

    def encode(self, text):
        return np.array([TOKENS[text]] if text in TOKENS else [ord(c) % 32 for c in text] or [0], dtype=np.int64)

    def embed(self, ids):
        return self.table[np.asarray(ids)][None]

    def last_hidden(self, embeds):
        return self.hidden

    def label_rows(self, ids):
        self.label_row_calls.append(list(ids))
        return self.table[np.asarray(ids)]


def _ov():
    ov = pytest.importorskip("openvino")
    from openvino import opset13 as ops
    return ov, ops


def _patch(digest):
    return SimpleNamespace(digest=digest)


@pytest.fixture
def runtime_tracker(monkeypatch):
    built = []

    class CountingRuntime(FakeRuntime):
        def __init__(self, ir_dir, device="CPU", token_patch=None):
            super().__init__(device=device)
            self.token_patch_digest = getattr(token_patch, "digest", None)
            built.append((ir_dir, device, self.token_patch_digest))

    monkeypatch.setattr(rt_mod, "BackboneRuntime", CountingRuntime)
    monkeypatch.setattr(rt_mod, "_RUNTIMES", WeakValueDictionary())
    return built


@pytest.mark.unit
def test_classifier_basics():
    fake = FakeRuntime()
    clf = OVQwenClassifier(ov_model="/unused", runtime=fake)
    expected = fake.table[[TOKENS["E"], TOKENS["H"]]].astype(np.float64) @ fake.hidden.astype(np.float64)
    result = clf.classify("What is 2 + 2?")
    assert fake.label_row_calls == [[TOKENS["E"], TOKENS["H"]]]
    assert result.raw["label_logits"] == pytest.approx(dict(zip(("E", "H"), expected)))
    assert result.scores == pytest.approx(label_scores(expected, ["E", "H"]))
    assert OVQwenClassifier(ov_model="/unused", device="GPU.1", runtime=FakeRuntime()).device == "CPU"
    with pytest.raises(ValueError, match="not single tokens"):
        OVQwenClassifier(ov_model="/unused", labels=["E", "Hard"], runtime=FakeRuntime())


@pytest.mark.unit
def test_classifiers_share_runtime_and_release_it(runtime_tracker, tmp_path):
    a = OVQwenClassifier(ov_model=str(tmp_path), device="CPU", system_prompt="a")
    b = OVQwenClassifier(ov_model=str(tmp_path / "x" / ".."), device="CPU", system_prompt="b")
    assert a._runtime is b._runtime and len(runtime_tracker) == 1
    c = OVQwenClassifier(ov_model=str(tmp_path), device="GPU", system_prompt="a")
    assert c._runtime is not a._runtime and len(runtime_tracker) == 2
    runtime = weakref.ref(a._runtime)
    del a, b
    gc.collect()
    assert runtime() is None
    OVQwenClassifier(ov_model=str(tmp_path), device="CPU", system_prompt="a")
    assert len(runtime_tracker) == 3


@pytest.mark.unit
@pytest.mark.parametrize("config,tied", [
    ({"tie_word_embeddings": True}, True),
    ({"tie_word_embeddings": False}, False),
    ({"tie_word_embeddings": False, "text_config": {"tie_word_embeddings": True}}, True),
    ({}, True),
])
def test_tied_embeddings_from_config(tmp_path, config, tied):
    (tmp_path / "config.json").write_text(json.dumps(config))
    assert rt_mod._tied_embeddings(tmp_path) is tied


# -- graph surgery on a synthetic lm_head -------------------------------------

def _toy_lm(weight=None, transpose_b=True, compressed=False, weight_node=None):
    ov, ops = _ov()
    x = ops.parameter(ov.PartialShape([1, -1, HIDDEN]), ov.Type.f32, name="inputs_embeds")
    hidden = ops.multiply(x, np.float32(2.0))
    if weight_node is None:
        w = weight if transpose_b else weight.T
        if compressed:
            scale = np.float32(0.5)
            weight_node = ops.multiply(
                ops.convert(ops.constant(np.round(w / scale).astype(np.uint8)), ov.Type.f32), scale
            )
        else:
            weight_node = ops.constant(w.astype(np.float32))
    matmul = ops.matmul(hidden, weight_node, False, transpose_b)
    matmul.set_friendly_name("__module.lm_head/MatMul")
    logits = ops.result(matmul)
    logits.output(0).get_tensor().set_names({"logits"})
    return ov.Model([logits], [x], "toy"), ov


@pytest.mark.unit
@pytest.mark.parametrize("transpose_b", [True, False])
@pytest.mark.parametrize("compressed", [False, True])
def test_head_rows_and_hidden_reproduce_vocab_logits(transpose_b, compressed):
    weight = np.arange(10 * HIDDEN, dtype=np.float32).reshape(10, HIDDEN) % 7
    model, ov = _toy_lm(weight, transpose_b, compressed)
    core = ov.Core()
    x = np.random.default_rng(0).normal(size=(1, 3, HIDDEN)).astype(np.float32)
    vocab_logits = core.compile_model(model.clone(), "CPU")(x)[0][0, -1]
    rows = core.compile_model(rt_mod._head_rows_model(rt_mod._lm_head_matmul(model)), "CPU")(
        np.array([3, 8])
    )[0]
    np.testing.assert_array_equal(rows, weight[[3, 8]])
    lm = rt_mod._expose_hidden(model)
    assert [o.get_names() for o in lm.outputs] == [{rt_mod.HIDDEN_NAME}]
    hidden = core.compile_model(lm, "CPU")(x)[0][0, -1]
    np.testing.assert_allclose(rows @ hidden, vocab_logits[[3, 8]], rtol=1e-5)


def _toy_linear_attention():
    ov, ops = _ov()
    x = ops.parameter(ov.PartialShape([1, -1, HIDDEN]), ov.Type.f32, name="inputs_embeds")
    mask = ops.parameter(ov.PartialShape([1, -1]), ov.Type.i64, name="attention_mask")
    mask.output(0).get_tensor().set_names({"attention_mask"})
    normed = ops.multiply(x, np.float32(1.5))
    outs = []
    for name in ("in_proj_qkv", "in_proj_z"):
        mm = ops.matmul(normed, ops.constant(np.eye(HIDDEN, dtype=np.float32)), False, False)
        mm.set_friendly_name(f"model.layers.0.linear_attn.{name}/MatMul")
        outs.append(ops.result(mm))
    outs.append(ops.result(ops.shape_of(normed)))
    return ov.Model(outs, [x, mask], "toy_gdn"), ov


@pytest.mark.unit
def test_linear_attention_masking_and_noop():
    model, ov = _toy_linear_attention()
    assert rt_mod._mask_linear_attention(model) == 1
    x = np.random.default_rng(0).normal(size=(1, 4, HIDDEN)).astype(np.float32)
    out = ov.Core().compile_model(model, "CPU")([x, np.array([[1, 0, 0, 1]], dtype=np.int64)])
    for i in (0, 1):
        np.testing.assert_allclose(out[i][0, [0, 3]], 1.5 * x[0, [0, 3]], rtol=1e-6)
        np.testing.assert_array_equal(out[i][0, [1, 2]], 0)
    assert list(out[2]) == [1, 4, HIDDEN]
    plain, _ = _toy_lm(np.ones((V, HIDDEN), np.float32))
    assert rt_mod._mask_linear_attention(plain) == 0


@pytest.mark.unit
def test_keep_last_logits_keeps_full_vocab_at_last_position():
    model, ov = _toy_lm(W)
    core = ov.Core()
    full = core.compile_model(model.clone(), "CPU")(XIN)[0]
    kept = rt_mod._keep_last_logits(model)
    out = core.compile_model(kept, "CPU").create_infer_request().infer({0: XIN})
    assert sorted(o.get_any_name() for o in kept.outputs) == ["last_hidden_state", "logits"]
    assert out[0].shape == (1, V)
    np.testing.assert_allclose(out[0][0], full[0, -1], atol=1e-5)
    np.testing.assert_allclose(out[1][0, -1], 2.0 * XIN[0, -1], atol=1e-6)


@pytest.mark.unit
def test_bf16_row_patch_keeps_other_weights_compressed():
    ov, ops = _ov()
    x = ops.parameter(ov.PartialShape([1, -1, HIDDEN]), ov.Type.f32, name="inputs_embeds")
    other = ops.convert(ops.constant(np.eye(HIDDEN, dtype=np.float32), ov.Type.bf16), ov.Type.f32)
    other16 = ops.convert(ops.constant(np.eye(HIDDEN, dtype=np.float32), ov.Type.f16), ov.Type.f32)
    hidden = ops.matmul(ops.matmul(x, other, False, False), other16, False, False)
    table = ops.convert(ops.constant(W * 0.01, ov.Type.bf16), ov.Type.f32)
    matmul = ops.matmul(hidden, table, False, True)
    matmul.set_friendly_name("lm_head")
    model = ov.Model([ops.result(matmul)], [x])
    converts_before = sum(op.get_type_name() == "Convert" for op in model.get_ops())
    rt_mod._patch_table_rows(ov.Core(), rt_mod._lm_head_matmul(model).input(1),
                             {7: np.full(HIDDEN, 0.02, np.float32)}, "lm_head")
    model.validate_nodes_and_infer_types()
    constants = [op.get_element_type() for op in model.get_ops()
                 if op.get_type_name() == "Constant"
                 and op.get_output_partial_shape(0).rank.get_length() == 2]
    assert sorted(map(str, constants)) == sorted(["<Type: 'bfloat16'>", "<Type: 'float16'>", "<Type: 'float32'>"])
    assert sum(op.get_type_name() == "Convert" for op in model.get_ops()) == converts_before
    logits = ov.Core().compile_model(model, "CPU")(np.ones((1, 1, HIDDEN), np.float32))[0][0, -1]
    assert logits[7] == pytest.approx(0.02 * HIDDEN, rel=0.02)


@pytest.mark.unit
def test_patch_table_rows_replaces_row_only():
    ov, ops = _ov()
    model, _ = _toy_lm(weight_node=ops.constant(W))
    core = ov.Core()
    before = core.compile_model(model.clone(), "CPU")(XIN)[0][0, -1]
    row = np.full(HIDDEN, 3.25, np.float32)
    rt_mod._patch_table_rows(core, rt_mod._lm_head_matmul(model).input(1), {7: row}, "test")
    after = core.compile_model(model, "CPU")(XIN)[0][0, -1]
    assert after[7] == pytest.approx(float(row @ (2.0 * XIN[0, -1])), abs=1e-4)
    np.testing.assert_array_equal(np.delete(after, 7), np.delete(before, 7))


@pytest.mark.unit
@pytest.mark.parametrize("etype", ["f16", "bf16"])
def test_patch_converted_table_rounds_only(etype):
    ov, ops = _ov()
    w = (np.random.default_rng(2).normal(size=(V, HIDDEN)) * 0.01).astype(np.float32)
    model, _ = _toy_lm(weight_node=ops.convert(ops.constant(w, getattr(ov.Type, etype)), ov.Type.f32))
    core, ones = ov.Core(), np.ones((1, 1, HIDDEN), np.float32)
    before = core.compile_model(model.clone(), "CPU")(ones)[0][0, -1]
    row = np.array([0.0123, -0.0456, 0.0789, 0.001], np.float32)[:HIDDEN]
    rt_mod._patch_table_rows(core, rt_mod._lm_head_matmul(model).input(1), {5: row}, etype)
    after = core.compile_model(model, "CPU")(ones)[0][0, -1]
    np.testing.assert_array_equal(np.delete(before, 5), np.delete(after, 5))
    assert abs(after[5] - float(row @ (2.0 * np.ones(HIDDEN)))) < 1.5e-3


@pytest.mark.unit
def test_patch_table_columns_for_untransposed_weight():
    ov, ops = _ov()
    model, _ = _toy_lm(weight_node=ops.constant(W.T.copy()), transpose_b=False)
    core = ov.Core()
    row = np.array([1.25, -2.5, 3.75, -4.0], np.float32)[:HIDDEN]
    rt_mod._patch_table_rows(core, rt_mod._lm_head_matmul(model).input(1), {5: row}, "cols", columns=True)
    rt_mod._keep_last_logits(model)
    logits = core.compile_model(model, "CPU").create_infer_request().infer({0: XIN})[0][0]
    assert logits[5] == pytest.approx(float(row @ (2.0 * XIN[0, -1])), abs=1e-4)


@pytest.mark.unit
def test_weight_compressed_tables_are_rejected():
    ov, ops = _ov()
    x = ops.parameter(ov.PartialShape([1, -1, HIDDEN]), ov.Type.f32)
    w = ops.multiply(ops.convert(ops.constant(np.full((V, HIDDEN), 2, np.uint8)), ov.Type.f32), np.float32(0.5))
    matmul = ops.matmul(x, w, False, True)
    matmul.set_friendly_name("lm_head")
    model = ov.Model([ops.result(matmul)], [x])
    with pytest.raises(rt_mod.TokenFormError, match="FP16/BF16"):
        rt_mod._patch_table_rows(ov.Core(), rt_mod._lm_head_matmul(model).input(1),
                                 {5: np.zeros(HIDDEN)}, "w")


@pytest.mark.unit
@pytest.mark.parametrize("direct", [False, True], ids=["converted", "direct"])
def test_embedding_tables_are_found_and_patched(direct):
    ov, ops = _ov()
    ids = ops.parameter(ov.PartialShape([-1]), ov.Type.i64, name="input_ids")
    table = ops.constant(np.ones((V, HIDDEN), np.float32) if direct else np.zeros((V, HIDDEN), np.float32), ov.Type.bf16)
    source = table if direct else ops.convert(table, ov.Type.f32)
    gather = ops.gather(source, ids, np.array(0))
    gather.set_friendly_name("ov_ext::embedding/Gather")
    model = ov.Model([ops.result(gather)], [ids], "text_embeddings")
    table_input = gather.input(0) if direct else rt_mod._embedding_table_input(model)
    rt_mod._patch_table_rows(ov.Core(), table_input, {7 if direct else 4: np.full(HIDDEN, 0.5, np.float32)}, "emb")
    index = 7 if direct else 4
    read = ov.Core().compile_model(model, "CPU")(np.array([0, index], np.int64))[0]
    np.testing.assert_allclose(read[1], 0.5, atol=1e-3 if direct else 0.01)
    if direct:
        assert float(read[0, 0]) == 1.0


@pytest.mark.unit
def test_runtime_cache_patch_selection(runtime_tracker, tmp_path):
    ir = str(tmp_path)
    patched = rt_mod.get_runtime(ir, "CPU", token_patch=_patch("aaa"))
    assert rt_mod.get_runtime(ir, "CPU") is patched and len(runtime_tracker) == 1
    assert rt_mod.get_runtime(ir, "CPU", token_patch=_patch("bbb")) is not patched
    assert rt_mod.get_runtime(str(tmp_path / "sub"), "CPU") is not patched
    assert len(runtime_tracker) == 3


@pytest.mark.unit
def test_classifier_runtime_switching(runtime_tracker, tmp_path):
    ir = str(tmp_path)
    clf = OVQwenClassifier(ov_model=ir, device="CPU", labels=["E", "H"])
    unpatched = clf._runtime
    assert [x[2] for x in runtime_tracker] == [None]
    patched = rt_mod.get_runtime(ir, "CPU", token_patch=_patch("aaa"))
    clf.classify("hello")
    assert clf._runtime is patched and [x[2] for x in runtime_tracker] == [None, "aaa"]
    del unpatched
    gc.collect()
    assert [key[2] for key in rt_mod._RUNTIMES] == ["aaa"]
    assert rt_mod.get_runtime(ir, "CPU") is patched

    injected = FakeRuntime()
    clf = OVQwenClassifier(ov_model=ir, labels=["E", "H"], runtime=injected)
    clf.classify("hello")
    assert clf._runtime is injected


@pytest.mark.unit
def test_bf16_table_without_a_convert_is_patched():
    """A bf16 constant feeding the consumer directly (no Convert in between):
    the reported crash -- _backing_constant handed back an Output, which has
    no replace_source_output. The patch must land and the other rows stay."""
    ov = pytest.importorskip("openvino")
    from openvino import opset13 as ops

    ids = ops.parameter(ov.PartialShape([-1]), ov.Type.i64, name="input_ids")
    gather = ops.gather(
        ops.constant(np.ones((V, HIDDEN), np.float32), ov.Type.bf16), ids, np.array(0)
    )
    model = ov.Model([ops.result(gather)], [ids], "direct_bf16")

    rt_mod._patch_table_rows(
        ov.Core(), gather.input(0), {7: np.full(HIDDEN, 0.5, np.float32)}, "emb"
    )
    read = ov.Core().compile_model(model, "CPU")(np.array([0, 7], np.int64))[0]
    np.testing.assert_allclose(read[1], 0.5, atol=1e-3)  # the written row
    assert float(read[0, 0]) == 1.0  # untouched rows keep their values


@pytest.mark.unit
def test_patch_table_rows_resizes_a_table_without_free_rows():
    """A backbone whose tokenizer uses the whole vocabulary (llama3-1b): ids
    past the table's end grow the constant, written rows land, and the rows
    the version does not write stay zero and are never addressed."""
    ov = pytest.importorskip("openvino")
    from openvino import opset13 as ops

    model, _ = _toy_lm(weight_node=ops.constant(W))
    row = np.full(HIDDEN, 3.5, np.float32)
    rt_mod._patch_table_rows(
        ov.Core(), rt_mod._lm_head_matmul(model).input(1), {V + 3: row}, "test",
        target_rows=V + 8,
    )
    rt_mod._keep_last_logits(model)
    logits = ov.Core().compile_model(model, "CPU").create_infer_request().infer({0: XIN})[0][0]
    assert logits.shape == (V + 8,)  # grown to the target size
    assert logits[V + 3] == pytest.approx(float(row @ (2.0 * XIN[0, -1])), abs=1e-4)
    reference_model, _ = _toy_lm(weight_node=ops.constant(W))  # unpatched twin
    untouched = ov.Core().compile_model(reference_model, "CPU")(XIN)[0][0, -1]
    np.testing.assert_array_equal(logits[:V], untouched)  # originals unchanged
    reserve = np.delete(logits[V:], 3)  # the reserve rows except the written one
    assert (reserve == 0).all()  # stay zero: never addressed
