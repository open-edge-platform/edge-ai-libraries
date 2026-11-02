# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""L3 accuracy/function tests for the production KVWeave LMCache serde codec.

Covers KVW3 (quantized) and KVW0 (raw) payloads; shared helpers are in serde_helpers.py.
"""
from __future__ import annotations

import pytest
import torch

from conftest import (
    PROD_HEAD_DIM,
    PROD_NUM_KV_HEADS,
    generate_chunk,
    requires_xpu,
)
from serde_helpers import (
    kvweave_quant,
    kvweave_serde,
    _KVWeaveCodec,
    _assert_close_to_source,
    _attention_chunk_3d,
    _attention_chunk_4d,
    _codec,
    _cpu_dequantize_into_4d,
    _cpu_dequantize_into_4d_with_thread_strategy,
    _parse_payload,
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

        parsed = _parse_payload(codec, payload)
        assert parsed["raw"] is False
        assert parsed["shape"] == tuple(source.shape)

        restored = torch.empty_like(source)
        codec.deserialize_tensor(_payload_tensor(payload), restored)
        _assert_close_to_source(restored, source)

    @pytest.mark.parametrize(
        "device", ["cpu", pytest.param("xpu", marks=requires_xpu)]
    )
    def test_encode_chunk_into_fused_matches_encode_chunk(self, device):
        """encode_chunk_into must write the same payload encode_chunk returns (the
        XPU module writes it straight into the slot), leave the slot tail
        untouched, and decode back within threshold."""
        from lmcache.v1.distributed.serde.kvweave.kvweave_config import AttentionPlaneLayout

        codec = _codec(device=device, scaling_method="per_token")
        layers, tokens, hidden = 8, 1024, 2 * PROD_NUM_KV_HEADS * PROD_HEAD_DIM
        raw = torch.randn(layers, tokens, hidden).clamp(-0.3, 0.3).to(torch.float16)
        head = ("attention", None, 64, None)
        layout = AttentionPlaneLayout.FUSED_KV

        expected = codec.encode_chunk(*head, raw, layout)
        slot = torch.full((len(expected) + 777,), 0xAB, dtype=torch.uint8)
        n = codec.encode_chunk_into(*head, raw, slot, layout)

        assert n == len(expected)
        if device == "xpu":
            # The CPU native embeds a per-call scale id, so only the XPU
            # module's payload is reproducible byte-for-byte across calls.
            assert bytes(slot[:n].numpy()) == expected
        assert bool((slot[n:] == 0xAB).all())

        restored = codec.decode_chunk(
            "attention", None, 64, raw.shape, raw.dtype, slot[:n], layout
        )
        _assert_close_to_source(restored, raw)

    @pytest.mark.parametrize(
        "device", ["cpu", pytest.param("xpu", marks=requires_xpu)]
    )
    def test_encode_chunk_into_fused_rejects_small_destination(self, device):
        from lmcache.v1.distributed.serde.kvweave.kvweave_config import AttentionPlaneLayout

        codec = _codec(device=device, scaling_method="per_token")
        raw = torch.randn(2, 1024, 2 * PROD_NUM_KV_HEADS * PROD_HEAD_DIM).to(torch.float16)
        layout = AttentionPlaneLayout.FUSED_KV
        needed = len(codec.encode_chunk("attention", None, 64, None, raw, layout))
        with pytest.raises(ValueError):
            codec.encode_chunk_into(
                "attention", None, 64, None, raw,
                torch.empty(needed - 1, dtype=torch.uint8), layout,
            )

    @requires_xpu
    def test_fused_decode_into_matches_tensor_api_path(self, monkeypatch):
        """On XPU, decoding a fused chunk through the _into entry point must be
        bit-identical to the tensor-returning + merge path."""
        from lmcache.v1.distributed.serde.kvweave.kvweave_config import AttentionPlaneLayout

        codec = _codec(device="xpu", scaling_method="per_token", fused_direct_dequant=False)
        layers, tokens, hidden = 8, 1024, 2 * PROD_NUM_KV_HEADS * PROD_HEAD_DIM
        raw = torch.randn(layers, tokens, hidden).clamp(-0.3, 0.3).to(torch.float16)
        layout = AttentionPlaneLayout.FUSED_KV
        payload = codec.encode_chunk("attention", None, 64, None, raw, layout)
        chunk = _payload_tensor(payload)

        calls = []
        native = codec.native
        original = native.kvweave_dequantize_chunk_state_into
        monkeypatch.setattr(
            native, "kvweave_dequantize_chunk_state_into",
            lambda *a, **k: (calls.append(1), original(*a, **k))[1],
        )
        via_into = torch.empty_like(raw)
        codec.decode_chunk("attention", None, 64, raw.shape, raw.dtype, chunk, layout, via_into)
        assert calls, "decode did not use the _into entry point"

        monkeypatch.delattr(native, "kvweave_dequantize_chunk_state_into")
        via_tensor_api = torch.empty_like(raw)
        codec.decode_chunk("attention", None, 64, raw.shape, raw.dtype, chunk, layout, via_tensor_api)
        assert torch.equal(via_into, via_tensor_api)
        _assert_close_to_source(via_into, raw)

    @pytest.mark.parametrize("size", [128, 2048, 4096])
    def test_mamba_precond_pair_is_stable_across_calls(self, size):
        """The native precond cache is keyed by the perm tensor's address, so the
        Mamba P/D pair must be the same tensors on every call -- with unchanged contents."""
        first_signs, first_perm = _KVWeaveCodec._mamba_precond_pair(size)
        again_signs, again_perm = _KVWeaveCodec._mamba_precond_pair(size)
        assert first_perm.data_ptr() == again_perm.data_ptr()
        assert first_signs.data_ptr() == again_signs.data_ptr()
        fresh_signs, fresh_perm = kvweave_serde.KVWeaveCodecConfig().mamba_precond_tensors(size)
        assert torch.equal(first_signs, fresh_signs)
        assert torch.equal(first_perm, fresh_perm)

    @pytest.mark.parametrize("scaling_method", ["per_channel", "per_token"])
    def test_attention_precond_is_applied_and_roundtrips(self, scaling_method):
        """precond=True must change the quantized payload (P/D actually applied),
        and the header flag must let deserialize invert it."""
        source = _attention_chunk_4d(chunk_tokens=1024, num_layers=2, seed=5)
        payloads = {}
        for precond in (False, True):
            codec = _codec(scaling_method=scaling_method, precond=precond)
            payload = codec.serialize_tensor(source)
            assert _parse_payload(codec, payload)["rh"] is True
            restored = torch.empty_like(source)
            codec.deserialize_tensor(_payload_tensor(payload), restored)
            _assert_close_to_source(restored, source)
            payloads[precond] = _parse_payload(codec, payload)["q_data"]

        assert payloads[False] != payloads[True]

        # A codec configured with precond=False must still decode a precond=True
        # payload correctly: decode follows the header flag, not local config.
        restored = torch.empty_like(source)
        _codec(scaling_method=scaling_method, precond=False).deserialize_tensor(
            _payload_tensor(_codec(scaling_method=scaling_method, precond=True).serialize_tensor(source)),
            restored,
        )
        _assert_close_to_source(restored, source)

    def test_attention_4d_multilayer_dequantize_uses_direct_path_into_dst(self, monkeypatch):
        if not hasattr(kvweave_quant, "kvweave_dequantize_chunk_into_4d"):
            pytest.skip("direct 4D dequant path is not available")

        codec = _codec(num_threads=4)
        source = _attention_chunk_4d(chunk_tokens=64, num_layers=3, seed=24)
        payload = codec.serialize_tensor(source)
        parsed = _parse_payload(codec, payload)

        direct = torch.empty_like(source)
        _cpu_dequantize_into_4d(codec, parsed, direct)
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

        _cpu_dequantize_into_4d(codec, parsed, direct)
        _cpu_dequantize_into_4d_with_thread_strategy(
            parsed,
            by_layer,
            block_num_threads=1,
            layer_num_threads=4,
        )

        assert torch.equal(by_layer, direct), scenario
        _assert_close_to_source(by_layer, source)

    def test_non_attention_shape_is_rejected_for_quantized_codec(self):
        codec = _codec(num_kv_heads=PROD_NUM_KV_HEADS, head_dim=PROD_HEAD_DIM)
        source = generate_chunk(
            chunk_tokens=64,
            head_num=1,
            head_dim=768,
            dtype=torch.float16,
            seed=3,
        )

        with pytest.raises(ValueError, match="hidden size"):
            codec.serialize_tensor(source)

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

    @pytest.mark.parametrize(
        "device", ["cpu", pytest.param("xpu", marks=requires_xpu)]
    )
    @pytest.mark.parametrize("scaling_method", ["per_channel", "per_token"])
    @pytest.mark.parametrize("precond", [False, True], ids=["no_precond", "precond"])
    def test_fused_direct_quant_matches_split_path(
        self, monkeypatch, device, scaling_method, precond
    ):
        """serialize_fused_tensor must route through the native direct kernel
        when available, and decode as accurately as the head-split path."""
        from lmcache.v1.distributed.serde.kvweave.kvweave_config import AttentionPlaneLayout

        settings = dict(device=device, scaling_method=scaling_method, precond=precond)
        direct = _codec(**settings)
        split = _codec(**settings, fused_direct_quant=False)
        if not direct.supports_fused_direct_quant():
            pytest.skip("native build lacks kvweave_serialize_fused_chunk_direct")
        layers, tokens, hidden = 4, 1024, 2 * PROD_NUM_KV_HEADS * PROD_HEAD_DIM
        source = torch.randn(layers, tokens, hidden).clamp(-0.3, 0.3).to(torch.float16)

        calls = []
        original = direct.native.kvweave_serialize_fused_chunk_direct
        monkeypatch.setattr(
            direct.native, "kvweave_serialize_fused_chunk_direct",
            lambda *a, **k: (calls.append(1), original(*a, **k))[1],
        )
        direct_payload = direct.serialize_fused_tensor(source)
        assert calls, "serialize_fused_tensor did not use the direct kernel"
        split_payload = split.serialize_fused_tensor(source)
        assert len(direct_payload) == len(split_payload)

        slot = torch.full((len(direct_payload) + 99,), 0xAB, dtype=torch.uint8)
        written = direct.encode_chunk_into(
            "attention", None, 64, None, source, slot, AttentionPlaneLayout.FUSED_KV
        )
        assert written == len(direct_payload)
        assert bool((slot[written:] == 0xAB).all())

        restored_direct = torch.empty_like(source)
        restored_split = torch.empty_like(source)
        direct.deserialize_fused_tensor(_payload_tensor(direct_payload), restored_direct)
        split.deserialize_fused_tensor(_payload_tensor(split_payload), restored_split)
        _assert_close_to_source(restored_direct, source)
        mse_direct = (restored_direct.float() - source.float()).pow(2).mean().item()
        mse_split = (restored_split.float() - source.float()).pow(2).mean().item()
        assert abs(mse_direct - mse_split) <= 1e-3 * mse_split

    @pytest.mark.parametrize(
        "device", ["cpu", pytest.param("xpu", marks=requires_xpu)]
    )
    @pytest.mark.parametrize("scaling_method", ["per_channel", "per_token"])
    @pytest.mark.parametrize("precond", [False, True], ids=["no_precond", "precond"])
    def test_fused_direct_dequant_matches_split_path(
        self, monkeypatch, device, scaling_method, precond
    ):
        """deserialize_fused_tensor must route through the native direct dequant
        when available and produce exactly what the split + merge path does."""
        settings = dict(device=device, scaling_method=scaling_method, precond=precond)
        direct = _codec(**settings)
        split = _codec(**settings, fused_direct_dequant=False)
        if not direct.supports_fused_direct_dequant():
            pytest.skip("native build lacks kvweave_dequantize_fused_chunk_direct")
        layers, tokens, hidden = 4, 1024, 2 * PROD_NUM_KV_HEADS * PROD_HEAD_DIM
        source = torch.randn(layers, tokens, hidden).clamp(-0.3, 0.3).to(torch.float16)
        payload = _payload_tensor(direct.serialize_fused_tensor(source))

        calls = []
        original = direct.native.kvweave_dequantize_fused_chunk_direct
        monkeypatch.setattr(
            direct.native, "kvweave_dequantize_fused_chunk_direct",
            lambda *a, **k: (calls.append(1), original(*a, **k))[1],
        )
        via_direct = torch.empty_like(source)
        direct.deserialize_fused_tensor(payload, via_direct)
        assert calls, "deserialize_fused_tensor did not use the direct dequant kernel"
        monkeypatch.undo()

        via_split = torch.empty_like(source)
        split.deserialize_fused_tensor(payload, via_split)
        assert torch.equal(via_direct, via_split)
        _assert_close_to_source(via_direct, source)
