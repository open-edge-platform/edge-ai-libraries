# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""L3 accuracy/function tests for the production KVWeave LMCache serde codec.

The lower-level fused API tests build a KVW2 header in test helpers.  These
tests exercise the current production codec itself, which writes/parses
KVW3 (quantized) and KVW0 (raw) payloads.

Shared codec helpers live in serde_helpers.py so the L3 perf file can reuse
them; importing that module also skip-guards the whole file when
kvweave_serde (sourced from the patched LMCache tree) is unavailable.
"""
from __future__ import annotations

import pytest
import torch

from conftest import (
    PROD_HEAD_DIM,
    PROD_NUM_KV_HEADS,
    generate_chunk,
)
from serde_helpers import (
    kvweave_quant,
    kvweave_serde,
    _KVWeaveCodec,
    _assert_close_to_source,
    _attention_chunk_3d,
    _attention_chunk_4d,
    _codec,
    _cpu_dequantize_into_4d_with_thread_strategy,
    _payload_tensor,
    _prepare_deserialize_case_4d,
)


class TestL3SerdeCodec:
    """Correctness tests for real KVW3/KVW0 codec framing."""

    def test_attention_4d_roundtrip_keeps_4d_layout(self):
        codec = _codec()
        source_3d = _attention_chunk_3d(seed=2)
        source = source_3d.permute(1, 0, 2).unsqueeze(1).contiguous()

        payload = codec.serialize_tensor(source)
        assert payload[:4] == b"KVW3"

        parsed = codec._parse_payload(payload)
        assert parsed["raw"] is False
        assert parsed["shape"] == tuple(source.shape)

        restored = torch.empty_like(source)
        codec.deserialize_tensor(_payload_tensor(payload), restored)
        _assert_close_to_source(restored, source)

    def test_attention_4d_multilayer_dequantize_uses_direct_path_into_dst(self, monkeypatch):
        if not hasattr(kvweave_quant, "kvweave_dequantize_chunk_into_4d"):
            pytest.skip("direct 4D dequant path is not available")

        codec = _codec(num_threads=4)
        source = _attention_chunk_4d(chunk_tokens=64, num_layers=3, seed=24)
        payload = codec.serialize_tensor(source)
        parsed = codec._parse_payload(payload)

        direct = torch.empty_like(source)
        codec._cpu_dequantize_into_4d(parsed, direct)
        _assert_close_to_source(direct, source)

        calls = []
        original = kvweave_quant.kvweave_dequantize_chunk_into_4d

        def _wrapped(*args, **kwargs):
            dst_tensor = args[3]
            calls.append(tuple(dst_tensor.shape))
            return original(*args, **kwargs)

        monkeypatch.setattr(kvweave_quant, "kvweave_dequantize_chunk_into_4d", _wrapped)

        restored = torch.empty_like(source)
        codec.deserialize_tensor(_payload_tensor(payload), restored)

        assert calls == [tuple(source.shape)]
        _assert_close_to_source(restored, source)

    @pytest.mark.parametrize(
        ("scenario", "scaling_method", "rh"),
        [
            ("per_channel_rh", "per_channel", True),
            ("per_token_rh", "per_token", True),
            ("per_tensor_rh", "per_tensor", True),
            ("per_channel_no_rh", "per_channel", False),
        ],
        ids=["per_channel_rh", "per_token_rh", "per_tensor_rh", "per_channel_no_rh"],
    )
    def test_attention_4d_multilayer_thread_strategy_variants_match_direct(
        self,
        scenario,
        scaling_method,
        rh,
    ):
        if not hasattr(kvweave_quant, "kvweave_dequantize_chunk_into_4d"):
            pytest.skip("direct 4D dequant path is not available")

        case = _prepare_deserialize_case_4d(
            4,
            seed=27,
            num_layers=6,
            chunk_tokens=64,
            scaling_method=scaling_method,
            rh=rh,
            include_restored_4d=False,
        )
        codec = case["codec"]
        parsed = case["parsed"]
        source = case["source"]
        direct = torch.empty_like(source)
        by_layer = torch.empty_like(source)

        codec._cpu_dequantize_into_4d(parsed, direct)
        _cpu_dequantize_into_4d_with_thread_strategy(
            parsed,
            by_layer,
            block_num_threads=1,
            layer_num_threads=4,
        )

        assert torch.equal(by_layer, direct), scenario
        _assert_close_to_source(by_layer, source)

    def test_non_attention_shape_falls_back_to_kvw0_raw(self):
        codec = _codec(num_kv_heads=PROD_NUM_KV_HEADS, head_dim=PROD_HEAD_DIM)
        source = generate_chunk(
            chunk_tokens=64,
            head_num=1,
            head_dim=768,
            dtype=torch.float16,
            seed=3,
        )

        payload = codec.serialize_tensor(source)
        assert payload[:4] == b"KVW0"

        parsed = codec._parse_payload(payload)
        assert parsed["raw"] is True
        restored = torch.empty_like(source)
        codec.deserialize_tensor(_payload_tensor(payload), restored)
        assert torch.equal(restored, source)

    def test_quantize_false_uses_kvw0_raw_for_attention_shape(self):
        codec = _codec(quantize=False)
        source = _attention_chunk_3d(chunk_tokens=64, seed=4)

        payload = codec.serialize_tensor(source)
        assert payload[:4] == b"KVW0"

        restored = torch.empty_like(source)
        codec.deserialize_tensor(_payload_tensor(payload), restored)
        assert torch.equal(restored, source)

    @pytest.mark.parametrize(
        ("h_merged", "expected"),
        [(PROD_NUM_KV_HEADS * PROD_HEAD_DIM, True), (768, False), (0, False)],
        ids=["attention", "shape_mismatch", "empty"],
    )
    def test_attention_shape_classification(self, h_merged, expected):
        codec = _codec()
        assert codec._is_attention_shape(h_merged) is expected

    def test_estimate_serialized_size_covers_actual_payload(self):
        codec = _codec()
        source = _attention_chunk_3d(seed=6)
        payload = codec.serialize_tensor(source)

        layout_desc = kvweave_serde.MemoryLayoutDesc(
            shapes=[torch.Size(source.shape)],
            dtypes=[source.dtype],
        )
        assert codec.estimate_serialized_size(layout_desc) >= len(payload)
