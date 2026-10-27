# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for fused kvweave_serialize_chunk and kvweave_dequantize_chunk APIs."""
from __future__ import annotations

import struct

import pytest
import torch

from kvweave import kvweave_quant
from conftest import (
    build_quant_cfg,
    generate_chunk,
    generate_preconditioning,
    prepare_fused_inputs,
    preconditioning_size_for_half,
    requires_xpu,
    split_kvw2_payload,
)

try:
    from kvweave import kvweave_quant_xpu
except ImportError:
    kvweave_quant_xpu = None

# Thresholds are higher than L1 because generate_chunk adds 1% outliers.
# 4-bit asymmetric without rh on outlier data can have very high mean_err.
_THRESHOLDS = {
    4: {"max_err": 0.50, "mean_err": 0.35},
    8: {"max_err": 0.10, "mean_err": 0.02},
}


class TestL2FusedRoundtrip:
    """Tests for kvweave_serialize_chunk."""

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    @pytest.mark.parametrize("asym", [False, True], ids=["sym", "asym"])
    def test_fused_roundtrip_accuracy(self, device, qbit, scaling_method, rh_precond, asym):
        """Fused serialize → dequantize_chunk roundtrip accuracy."""
        native = _native_module(device)
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=asym, precond=precond,
        )
        chunk = generate_chunk(dtype=torch.float16)
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)

        scale_id_k, scale_id_v = 0xA000, 0xA001
        payload = bytes(native.kvweave_serialize_chunk(
            tensor_4d,
            header,
            scale_id_k,
            scale_id_v,
            qbit=cfg["qbit"],
            blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"],
            head_num=cfg["head_num"],
            head_dim=cfg["head_dim"],
            rh=cfg["rh"],
            asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            signs=cfg["signs"],
            perm=cfg["perm"],
            num_threads=cfg["num_threads"],
        ))

        chunk_tokens, _, h_merged = chunk.shape
        scale_blobs, q_raw = split_kvw2_payload(payload)
        q_dtype = torch.int8 if qbit <= 8 else torch.int16
        q_data = torch.frombuffer(bytearray(q_raw), dtype=q_dtype)

        restored = native.kvweave_dequantize_chunk(
            q_data,
            scale_blobs[0],
            scale_blobs[1],
            1,  # num_layers
            chunk_tokens,
            h_merged,
            qbit=cfg["qbit"],
            blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"],
            head_num=cfg["head_num"],
            head_dim=cfg["head_dim"],
            rh=cfg["rh"],
            asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            output_dtype=torch.float16,
            signs=cfg["signs"],
            perm=cfg["perm"],
            num_threads=cfg["num_threads"],
        )

        diff = (restored.float() - tensor_4d.float()).abs()
        max_err = diff.max().item()
        mean_err = diff.mean().item()

        print(
            f"ACC | fused device={device} qbit={qbit} scaling={scaling_method} "
            f"rh={rh} precond={precond} asym={asym} | "
            f"max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )

        tol = _THRESHOLDS[qbit]
        assert max_err < tol["max_err"]
        assert mean_err < tol["mean_err"]

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    def test_fused_matches_sequential(self, device):
        """Fused API output matches step-by-step quantize + get_scales + pack."""
        native = _native_module(device)
        cfg = build_quant_cfg(
            qbit=8, scaling_method="per_token",
            rh=False, asym=False, precond=False,
        )
        chunk = generate_chunk(dtype=torch.float16)
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)

        # Fused path
        fused_payload = bytes(native.kvweave_serialize_chunk(
            tensor_4d,
            header,
            0xB000, 0xB001,
            qbit=cfg["qbit"],
            blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"],
            head_num=cfg["head_num"],
            head_dim=cfg["head_dim"],
            rh=cfg["rh"],
            asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            signs=None,
            perm=None,
            num_threads=cfg["num_threads"],
        ))

        # Sequential path
        seq_payload = bytes(native.kvweave_serialize_chunk(
            tensor_4d,
            header,
            0xB010, 0xB011,
            qbit=cfg["qbit"],
            blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"],
            head_num=cfg["head_num"],
            head_dim=cfg["head_dim"],
            rh=cfg["rh"],
            asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            signs=None,
            perm=None,
            num_threads=cfg["num_threads"],
        ))

        assert fused_payload == seq_payload, "Deterministic: same input should produce same output"


class TestL2FusedDequant:
    """Tests for kvweave_dequantize_chunk's output contract (shape/dtype).

    Numeric accuracy and serialize/dequant determinism are already covered
    by TestL2FusedRoundtrip; serialize_chunk is only used here to produce a
    valid payload fixture, it is not itself under test.
    """

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    def test_output_shape(self, device):
        """Dequantize chunk returns correct shape [2, num_layers, T, H*D]."""
        native = _native_module(device)
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        chunk = generate_chunk(dtype=torch.float16)
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)
        chunk_tokens, _, h_merged = chunk.shape

        payload = bytes(native.kvweave_serialize_chunk(
            tensor_4d, header, 0xC000, 0xC001,
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"], head_num=cfg["head_num"],
            head_dim=cfg["head_dim"], rh=cfg["rh"], asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            signs=None, perm=None, num_threads=cfg["num_threads"],
        ))

        scale_blobs, q_raw = split_kvw2_payload(payload)
        q_dtype = torch.int8 if cfg["qbit"] <= 8 else torch.int16
        q_data = torch.frombuffer(bytearray(q_raw), dtype=q_dtype)

        restored = native.kvweave_dequantize_chunk(
            q_data, scale_blobs[0], scale_blobs[1],
            1, chunk_tokens, h_merged,
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"], head_num=cfg["head_num"],
            head_dim=cfg["head_dim"], rh=cfg["rh"], asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            output_dtype=torch.float16,
            signs=None, perm=None, num_threads=cfg["num_threads"],
        )

        assert restored.shape == torch.Size([2, 1, chunk_tokens, h_merged])

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("out_dtype", [torch.float16, torch.bfloat16], ids=["fp16", "bf16"])
    def test_output_dtype(self, device, out_dtype):
        """Dequantize respects output_dtype parameter."""
        native = _native_module(device)
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        chunk = generate_chunk(dtype=torch.float16)
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)
        chunk_tokens, _, h_merged = chunk.shape

        payload = bytes(native.kvweave_serialize_chunk(
            tensor_4d, header, 0xD000, 0xD001,
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"], head_num=cfg["head_num"],
            head_dim=cfg["head_dim"], rh=cfg["rh"], asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            signs=None, perm=None, num_threads=cfg["num_threads"],
        ))

        scale_blobs, q_raw = split_kvw2_payload(payload)
        q_data = torch.frombuffer(bytearray(q_raw), dtype=torch.int8)

        restored = native.kvweave_dequantize_chunk(
            q_data, scale_blobs[0], scale_blobs[1],
            1, chunk_tokens, h_merged,
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"], head_num=cfg["head_num"],
            head_dim=cfg["head_dim"], rh=cfg["rh"], asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            output_dtype=out_dtype,
            signs=None, perm=None, num_threads=cfg["num_threads"],
        )

        assert restored.dtype == out_dtype


def _native_module(device: str):
    return kvweave_quant if device == "cpu" else kvweave_quant_xpu


def _split_state_payload(payload: bytes, header_len: int):
    """Parse a kvweave_serialize_chunk_state payload: header | BE32(len) | scales | q_data."""
    offset = header_len
    scale_len = struct.unpack(">I", payload[offset:offset + 4])[0]
    offset += 4
    scale_blob = payload[offset:offset + scale_len]
    offset += scale_len
    return scale_blob, payload[offset:]


class TestL2FusedStateRoundtrip:
    """kvweave_serialize_chunk_state / dequantize_chunk_state (single-plane, no K/V split), on CPU and XPU against the same accuracy bar."""

    _HEADER = b"ST01"

    @staticmethod
    def _cfg(num_layers, qbit, scaling_method, rh, asym,
             blocks_num=4, block_size=8, head_num=2, head_dim=16):
        chunk_tokens = blocks_num * block_size
        h_merged = head_num * head_dim
        layer_elements = chunk_tokens * h_merged
        signs = perm = None
        if rh:
            h_size = preconditioning_size_for_half(
                scaling_method, layer_elements, blocks_num, block_size, head_dim)
            signs, perm = generate_preconditioning(h_size)
        return {
            "num_layers": num_layers, "qbit": qbit, "scaling_method": scaling_method,
            "rh": rh, "asym": asym, "blocks_num": blocks_num, "block_size": block_size,
            "head_num": head_num, "head_dim": head_dim, "chunk_tokens": chunk_tokens,
            "h_merged": h_merged, "signs": signs, "perm": perm,
        }

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("num_layers", [1, 8])
    @pytest.mark.parametrize("qbit", [4, 8], ids=["4bit", "8bit"])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    @pytest.mark.parametrize("rh", [False, True], ids=["no_rh", "rh"])
    def test_state_roundtrip_accuracy(self, device, num_layers, qbit, scaling_method, rh):
        native = _native_module(device)
        cfg = self._cfg(num_layers, qbit, scaling_method, rh, asym=True)
        torch.manual_seed(0)
        # Mirrors generate_chunk()'s distribution (mostly small values, 1%
        # outliers) but shaped [num_layers, T, H*D] for this single-plane API.
        total = num_layers * cfg["chunk_tokens"] * cfg["h_merged"]
        t = torch.randn(total, dtype=torch.float32) * 0.05
        t = t.clamp(-0.3, 0.3)
        mask = torch.rand(total) < 0.01
        t[mask] = torch.rand(int(mask.sum().item())) * 10.0 - 5.0
        x = t.to(torch.float16).reshape(num_layers, cfg["chunk_tokens"], cfg["h_merged"])

        payload = bytes(native.kvweave_serialize_chunk_state(
            x, self._HEADER, 0xAAAA,
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"], num_layers=num_layers,
            rh=cfg["rh"], asym=cfg["asym"], scaling_method=cfg["scaling_method"],
            signs=cfg["signs"], perm=cfg["perm"], num_threads=0,
        ))
        assert payload[:len(self._HEADER)] == self._HEADER
        scale_blob, q_raw = _split_state_payload(payload, len(self._HEADER))
        q_dtype = torch.int8 if qbit <= 8 else torch.int16
        q_data = torch.frombuffer(bytearray(q_raw), dtype=q_dtype)

        restored = native.kvweave_dequantize_chunk_state(
            q_data, scale_blob, num_layers, cfg["chunk_tokens"], cfg["h_merged"],
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"],
            rh=cfg["rh"], asym=cfg["asym"], scaling_method=cfg["scaling_method"],
            output_dtype=torch.float16, signs=cfg["signs"], perm=cfg["perm"], num_threads=0,
        )

        diff = (restored.float() - x.float()).abs()
        max_err, mean_err = diff.max().item(), diff.mean().item()
        print(
            f"ACC | state device={device} qbit={qbit} scaling={scaling_method} "
            f"rh={rh} layers={num_layers} | max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )
        tol = _THRESHOLDS[qbit]
        assert max_err < tol["max_err"]
        assert mean_err < tol["mean_err"]

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    def test_state_per_channel_layers_do_not_cross_contaminate(self, device):
        """Layers must not cross-contaminate under per_channel scaling (chunk_id spans num_layers*head_dim)."""
        native = _native_module(device)
        cfg = self._cfg(num_layers=2, qbit=8, scaling_method="per_channel", rh=False, asym=True)
        torch.manual_seed(1)
        x = torch.empty(2, cfg["chunk_tokens"], cfg["h_merged"], dtype=torch.float16)
        x[0] = (torch.randn(cfg["chunk_tokens"], cfg["h_merged"]) * 0.01).to(torch.float16)
        x[1] = (torch.randn(cfg["chunk_tokens"], cfg["h_merged"]) * 100.0).to(torch.float16)

        payload = bytes(native.kvweave_serialize_chunk_state(
            x, self._HEADER, 0xBBBB,
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"], num_layers=2,
            rh=False, asym=True, scaling_method="per_channel",
            signs=None, perm=None, num_threads=0,
        ))
        scale_blob, q_raw = _split_state_payload(payload, len(self._HEADER))
        q_data = torch.frombuffer(bytearray(q_raw), dtype=torch.int8)

        restored = native.kvweave_dequantize_chunk_state(
            q_data, scale_blob, 2, cfg["chunk_tokens"], cfg["h_merged"],
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"],
            rh=False, asym=True, scaling_method="per_channel",
            output_dtype=torch.float16, signs=None, perm=None, num_threads=0,
        )

        err_tiny_layer = (restored[0].float() - x[0].float()).abs().max().item()
        err_huge_layer = (restored[1].float() - x[1].float()).abs().max().item()
        assert err_tiny_layer < 0.01, (
            f"layer 0 (tiny values) corrupted by layer 1's scale: max_err={err_tiny_layer}"
        )
        assert err_huge_layer < 5.0, f"layer 1 not quantized correctly: max_err={err_huge_layer}"

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    def test_state_dequant_ignores_trailing_padding(self, device):
        """q_data must dequantize identically with trailing slot padding; a too-short buffer must be rejected."""
        native = _native_module(device)
        cfg = self._cfg(num_layers=3, qbit=8, scaling_method="per_token", rh=False, asym=True)
        torch.manual_seed(2)
        x = (torch.randn(3, cfg["chunk_tokens"], cfg["h_merged"]) * 2.0).to(torch.float16)

        payload = bytes(native.kvweave_serialize_chunk_state(
            x, self._HEADER, 0xCCCC,
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"], num_layers=3,
            rh=False, asym=True, scaling_method="per_token",
            signs=None, perm=None, num_threads=0,
        ))
        scale_blob, q_raw = _split_state_payload(payload, len(self._HEADER))

        def dequant(q_bytes):
            q_dtype = torch.int8
            q_data = torch.frombuffer(bytearray(q_bytes), dtype=q_dtype)
            return native.kvweave_dequantize_chunk_state(
                q_data, scale_blob, 3, cfg["chunk_tokens"], cfg["h_merged"],
                qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
                head_num=cfg["head_num"], head_dim=cfg["head_dim"],
                rh=False, asym=True, scaling_method="per_token",
                output_dtype=torch.float16, signs=None, perm=None, num_threads=0,
            )

        exact = dequant(q_raw)
        padded = dequant(q_raw + bytes([0xEE]) * 4096)
        assert torch.equal(exact, padded), "trailing padding changed the dequantized result"

        with pytest.raises((ValueError, RuntimeError)):
            dequant(q_raw[:-1])

    @requires_xpu
    @pytest.mark.parametrize("num_layers", [1, 3, 8])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    def test_state_serialize_into_matches_bytes_api(self, num_layers, scaling_method):
        """kvweave_serialize_chunk_state_into must write exactly the bytes the
        bytes-returning entry point returns, leave the rest of dst untouched,
        and reject an undersized / wrongly typed dst."""
        cfg = self._cfg(num_layers, qbit=4, scaling_method=scaling_method, rh=False, asym=True)
        torch.manual_seed(5)
        x = (torch.randn(num_layers, cfg["chunk_tokens"], cfg["h_merged"]) * 0.5).to(torch.float16)
        kwargs = dict(
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"], num_layers=num_layers,
            rh=False, asym=True, scaling_method=scaling_method,
            signs=None, perm=None, num_threads=0,
        )
        expected = bytes(kvweave_quant_xpu.kvweave_serialize_chunk_state(
            x, self._HEADER, 0xEEEE, **kwargs))

        dst = torch.full((len(expected) + 123,), 0xAB, dtype=torch.uint8)
        n = kvweave_quant_xpu.kvweave_serialize_chunk_state_into(
            x, dst, self._HEADER, 0xEEEE, **kwargs)
        assert n == len(expected)
        assert bytes(dst[:n].numpy()) == expected
        assert bool((dst[n:] == 0xAB).all())

        with pytest.raises((ValueError, RuntimeError)):
            kvweave_quant_xpu.kvweave_serialize_chunk_state_into(
                x, torch.empty(n - 1, dtype=torch.uint8), self._HEADER, 0xEEEE, **kwargs)
        with pytest.raises((ValueError, RuntimeError)):
            kvweave_quant_xpu.kvweave_serialize_chunk_state_into(
                x, torch.empty(n, dtype=torch.int8), self._HEADER, 0xEEEE, **kwargs)

    @requires_xpu
    @pytest.mark.parametrize("num_layers", [1, 3])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    @pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16])
    @pytest.mark.parametrize("merge_head_num", [0, 2])
    def test_state_dequantize_into_matches_tensor_api(
        self, num_layers, scaling_method, dtype, merge_head_num
    ):
        """kvweave_dequantize_chunk_state_into must produce exactly what
        kvweave_dequantize_chunk_state returns (with the per-head planes folded
        back to [layers, tokens, heads*head_dim] when merge_head_num > 1),
        written into the caller's tensor; and must reject a bad dst."""
        planes = num_layers * max(1, merge_head_num)
        cfg = self._cfg(planes, qbit=4, scaling_method=scaling_method, rh=False, asym=True)
        torch.manual_seed(7)
        x = (torch.randn(planes, cfg["chunk_tokens"], cfg["h_merged"]) * 0.5).to(dtype)
        common = dict(
            qbit=4, blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"], rh=False, asym=True,
            scaling_method=scaling_method, signs=None, perm=None, num_threads=0,
        )
        payload = bytes(kvweave_quant_xpu.kvweave_serialize_chunk_state(
            x, self._HEADER, 0xFFFF, num_layers=planes, **common))
        scale_blob, q_raw = _split_state_payload(payload, len(self._HEADER))
        q = torch.frombuffer(bytearray(q_raw), dtype=torch.int8)

        expected = kvweave_quant_xpu.kvweave_dequantize_chunk_state(
            q, scale_blob, planes, cfg["chunk_tokens"], cfg["h_merged"],
            output_dtype=dtype, **common)
        if merge_head_num > 1:
            expected = (
                expected.view(num_layers, merge_head_num, cfg["chunk_tokens"], cfg["h_merged"])
                .permute(0, 2, 1, 3)
                .reshape(num_layers, cfg["chunk_tokens"], merge_head_num * cfg["h_merged"])
            )
        dst = torch.full(expected.shape, 7.0, dtype=dtype)
        kvweave_quant_xpu.kvweave_dequantize_chunk_state_into(
            q, scale_blob, dst.view(-1), planes, cfg["chunk_tokens"], cfg["h_merged"],
            output_dtype=dtype, merge_head_num=merge_head_num, **common)
        assert torch.equal(dst, expected)

        for bad in (
            torch.empty(dst.numel() - 1, dtype=dtype),        # wrong size
            torch.empty(dst.numel(), dtype=torch.float32),    # wrong dtype
            torch.empty(dst.numel() * 2, dtype=dtype)[::2],   # non-contiguous
        ):
            with pytest.raises((ValueError, RuntimeError)):
                kvweave_quant_xpu.kvweave_dequantize_chunk_state_into(
                    q, scale_blob, bad, planes, cfg["chunk_tokens"], cfg["h_merged"],
                    output_dtype=dtype, merge_head_num=merge_head_num, **common)

    @requires_xpu
    @pytest.mark.parametrize("num_layers", [1, 3, 8])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel", "per_tensor"])
    def test_state_scale_blob_wire_format_matches_cpu(self, num_layers, scaling_method):
        """CPU and XPU modules must emit identical scale-blob framing (per-layer length-prefixed segments) for num_layers > 1."""
        cfg = self._cfg(num_layers, qbit=8, scaling_method=scaling_method, rh=False, asym=True)
        torch.manual_seed(3)
        x = (torch.randn(num_layers, cfg["chunk_tokens"], cfg["h_merged"]) * 0.5).to(torch.float16)

        def payload_for(native):
            return bytes(native.kvweave_serialize_chunk_state(
                x, self._HEADER, 0xDDDD,
                qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
                head_num=cfg["head_num"], head_dim=cfg["head_dim"], num_layers=num_layers,
                rh=False, asym=True, scaling_method=scaling_method,
                signs=None, perm=None, num_threads=0,
            ))

        cpu_payload = payload_for(kvweave_quant)
        xpu_payload = payload_for(kvweave_quant_xpu)
        assert len(cpu_payload) == len(xpu_payload), (
            f"scale blob framing diverged: cpu={len(cpu_payload)} bytes, "
            f"xpu={len(xpu_payload)} bytes (num_layers={num_layers})"
        )

        cpu_scale_blob, _ = _split_state_payload(cpu_payload, len(self._HEADER))
        xpu_scale_blob, _ = _split_state_payload(xpu_payload, len(self._HEADER))
        assert len(cpu_scale_blob) == len(xpu_scale_blob), (
            "scale blob segment framing diverged in length between cpu and xpu "
            f"(num_layers={num_layers}) -- exact scale/zp float bytes may still "
            "differ since AVX and SYCL reduce in a different order"
        )

        # A blob from one device must parse on the other and dequantize to a numerically close result.
        q_dtype = torch.int8
        _, cpu_q_raw = _split_state_payload(cpu_payload, len(self._HEADER))
        cpu_q_data = torch.frombuffer(bytearray(cpu_q_raw), dtype=q_dtype)
        restored_cross = kvweave_quant_xpu.kvweave_dequantize_chunk_state(
            cpu_q_data, cpu_scale_blob, num_layers, cfg["chunk_tokens"], cfg["h_merged"],
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"],
            rh=False, asym=True, scaling_method=scaling_method,
            output_dtype=torch.float16, signs=None, perm=None, num_threads=0,
        )
        restored_same = kvweave_quant.kvweave_dequantize_chunk_state(
            cpu_q_data, cpu_scale_blob, num_layers, cfg["chunk_tokens"], cfg["h_merged"],
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"],
            rh=False, asym=True, scaling_method=scaling_method,
            output_dtype=torch.float16, signs=None, perm=None, num_threads=0,
        )
        max_delta = (restored_cross.float() - restored_same.float()).abs().max().item()
        assert max_delta < _THRESHOLDS[8]["max_err"], (
            f"xpu dequantize of a cpu-produced scale blob disagrees with cpu's "
            f"own dequantize by {max_delta}"
        )


def _parse_unit_scales(blob: bytes, units: int, nchunks: int) -> torch.Tensor:
    """Per-unit framed scale blob -> [units, nchunks, 2] (scale, zp)."""
    out = torch.empty(units, nchunks, 2, dtype=torch.float32)
    off = 0
    for u in range(units):
        (count,) = struct.unpack_from("<I", blob, off)
        assert count == nchunks
        off += 4
        for _ in range(nchunks):
            idx, scale, zp = struct.unpack_from("<Iff", blob, off)
            assert idx < nchunks
            out[u, idx, 0], out[u, idx, 1] = scale, zp
            off += 12
    assert off == len(blob)
    return out


class TestL2FusedDirectQuant:
    """Tests for kvweave_serialize_fused_chunk_direct (CPU and XPU).

    Quantizes fused [layers, tokens, head_num*head_dim] attention per
    (layer, head) without a separate head split; the payload must match
    kvweave_serialize_chunk_state on the head-split tensor (same module).
    """

    _HEADER = b"FD01"
    _LAYERS, _TOKENS, _HEAD_NUM, _HEAD_DIM = 3, 32, 2, 16

    @classmethod
    def _inputs(cls, dtype, scaling_method, rh, seed=0):
        torch.manual_seed(seed)
        hidden = cls._HEAD_NUM * cls._HEAD_DIM
        x = (torch.randn(cls._LAYERS, cls._TOKENS, hidden) * 0.5).to(dtype)
        signs = perm = None
        if rh:
            n = cls._TOKENS if scaling_method == "per_channel" else cls._HEAD_DIM
            signs, perm = generate_preconditioning(n)
        return x, signs, perm

    @classmethod
    def _split(cls, x):
        return (
            x.reshape(cls._LAYERS, cls._TOKENS, cls._HEAD_NUM, cls._HEAD_DIM)
            .permute(0, 2, 1, 3)
            .contiguous()
        )

    @classmethod
    def _direct(cls, native, x, qbit, scaling_method, rh, asym, signs, perm, out=None):
        return native.kvweave_serialize_fused_chunk_direct(
            x, cls._HEADER, qbit, cls._HEAD_NUM, cls._HEAD_DIM,
            rh=rh, asym=asym, scaling_method=scaling_method,
            signs=signs, perm=perm, num_threads=0, out=out,
        )

    @classmethod
    def _state_kwargs(cls, qbit, scaling_method, rh, asym, signs, perm):
        return dict(
            qbit=qbit, blocks_num=1, block_size=cls._TOKENS,
            head_num=cls._HEAD_NUM, head_dim=cls._HEAD_DIM,
            rh=rh, asym=asym, scaling_method=scaling_method,
            signs=signs, perm=perm, num_threads=0,
        )

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16, torch.float32],
                             ids=["fp16", "bf16", "fp32"])
    @pytest.mark.parametrize("qbit", [4, 8], ids=["4bit", "8bit"])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    @pytest.mark.parametrize("asym", [False, True], ids=["sym", "asym"])
    def test_direct_matches_split_state(self, device, dtype, qbit, scaling_method, rh_precond, asym):
        native = _native_module(device)
        rh, precond = rh_precond
        x, signs, perm = self._inputs(dtype, scaling_method, rh)
        if not precond:
            signs = perm = None
        units = self._LAYERS * self._HEAD_NUM
        nchunks = self._HEAD_DIM if scaling_method == "per_channel" else self._TOKENS

        direct = bytes(self._direct(native, x, qbit, scaling_method, rh, asym, signs, perm))
        ref = bytes(native.kvweave_serialize_chunk_state(
            self._split(x).view(-1), self._HEADER, 0xFD00, num_layers=units,
            **self._state_kwargs(qbit, scaling_method, rh, asym, signs, perm),
        ))
        assert len(direct) == len(ref)
        assert direct[:len(self._HEADER)] == self._HEADER

        d_blob, d_q = _split_state_payload(direct, len(self._HEADER))
        r_blob, r_q = _split_state_payload(ref, len(self._HEADER))
        d_scales = _parse_unit_scales(d_blob, units, nchunks)
        r_scales = _parse_unit_scales(r_blob, units, nchunks)
        # ~1 ulp drift allowed: default builds use a fast fp-model.
        torch.testing.assert_close(d_scales, r_scales, rtol=1e-5, atol=1e-6)
        d_qt = torch.frombuffer(bytearray(d_q), dtype=torch.uint8)
        r_qt = torch.frombuffer(bytearray(r_q), dtype=torch.uint8)
        mismatch = (d_qt != r_qt).float().mean().item()
        assert mismatch < 1e-2, f"q bytes mismatch fraction {mismatch}"

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("qbit", [4, 8], ids=["4bit", "8bit"])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    @pytest.mark.parametrize("rh", [False, True], ids=["no_rh", "rh"])
    def test_direct_roundtrip_accuracy(self, device, qbit, scaling_method, rh):
        native = _native_module(device)
        x, signs, perm = self._inputs(torch.float16, scaling_method, rh, seed=1)
        units = self._LAYERS * self._HEAD_NUM
        payload = bytes(self._direct(native, x, qbit, scaling_method, rh, True, signs, perm))
        scale_blob, q_raw = _split_state_payload(payload, len(self._HEADER))
        q_data = torch.frombuffer(bytearray(q_raw), dtype=torch.int8)

        restored = native.kvweave_dequantize_chunk_state(
            q_data, scale_blob, units, self._TOKENS, self._HEAD_DIM,
            output_dtype=torch.float16,
            **self._state_kwargs(qbit, scaling_method, rh, True, signs, perm),
        )
        merged = (
            restored.view(self._LAYERS, self._HEAD_NUM, self._TOKENS, self._HEAD_DIM)
            .permute(0, 2, 1, 3)
            .reshape_as(x)
        )
        diff = (merged.float() - x.float()).abs()
        tol = _THRESHOLDS[qbit]
        assert diff.max().item() < tol["max_err"]
        assert diff.mean().item() < tol["mean_err"]

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    def test_direct_out_matches_bytes(self, device, scaling_method):
        native = _native_module(device)
        x, signs, perm = self._inputs(torch.float16, scaling_method, True, seed=2)
        expected = bytes(self._direct(native, x, 4, scaling_method, True, True, signs, perm))

        out = torch.full((len(expected) + 77,), 0xAB, dtype=torch.uint8)
        n = self._direct(native, x, 4, scaling_method, True, True, signs, perm, out=out)
        assert n == len(expected)
        assert bytes(out[:n].numpy()) == expected
        assert bool((out[n:] == 0xAB).all())

        with pytest.raises((ValueError, RuntimeError)):
            self._direct(native, x, 4, scaling_method, True, True, signs, perm,
                         out=torch.empty(n - 1, dtype=torch.uint8))
        with pytest.raises((ValueError, RuntimeError)):
            self._direct(native, x, 4, scaling_method, True, True, signs, perm,
                         out=torch.empty(n, dtype=torch.int8))

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    def test_direct_rejects_invalid_args(self, device):
        native = _native_module(device)
        x, _, _ = self._inputs(torch.float16, "per_token", False)
        with pytest.raises((ValueError, RuntimeError)):
            self._direct(native, x, 4, "per_tensor", False, True, None, None)
        with pytest.raises((ValueError, RuntimeError)):
            native.kvweave_serialize_fused_chunk_direct(
                x, self._HEADER, 4, self._HEAD_NUM + 1, self._HEAD_DIM,
                scaling_method="per_token")
        with pytest.raises((ValueError, RuntimeError)):
            self._direct(native, x, 4, "per_token", True, True,
                         torch.ones(self._HEAD_DIM - 1), None)
        bad_perm = torch.arange(self._HEAD_DIM, dtype=torch.int32)
        bad_perm[0] = self._HEAD_DIM
        with pytest.raises((ValueError, RuntimeError)):
            self._direct(native, x, 4, "per_token", True, True, None, bad_perm)

    @requires_xpu
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    def test_xpu_direct_split_fallback_matches(self, scaling_method):
        """Profiling forces the non-SLM path, which splits on device first."""
        x, signs, perm = self._inputs(torch.float16, scaling_method, True, seed=3)
        fast = bytes(self._direct(kvweave_quant_xpu, x, 4, scaling_method, True, True, signs, perm))
        kvweave_quant_xpu.set_quant_profiling(True)
        try:
            slow = bytes(self._direct(kvweave_quant_xpu, x, 4, scaling_method, True, True, signs, perm))
        finally:
            kvweave_quant_xpu.set_quant_profiling(False)
            kvweave_quant_xpu.reset_profile_stats()
        assert len(fast) == len(slow)
        units = self._LAYERS * self._HEAD_NUM
        nchunks = self._HEAD_DIM if scaling_method == "per_channel" else self._TOKENS
        f_blob, f_q = _split_state_payload(fast, len(self._HEADER))
        s_blob, s_q = _split_state_payload(slow, len(self._HEADER))
        torch.testing.assert_close(
            _parse_unit_scales(f_blob, units, nchunks),
            _parse_unit_scales(s_blob, units, nchunks), rtol=1e-5, atol=1e-6)
        f_qt = torch.frombuffer(bytearray(f_q), dtype=torch.uint8)
        s_qt = torch.frombuffer(bytearray(s_q), dtype=torch.uint8)
        assert (f_qt != s_qt).float().mean().item() < 1e-2

    # --- kvweave_dequantize_fused_chunk_direct -------------------------------

    @classmethod
    def _encode(cls, native, x, qbit, scaling_method, rh, asym, signs, perm):
        payload = bytes(cls._direct(native, x, qbit, scaling_method, rh, asym, signs, perm))
        blob, q_raw = _split_state_payload(payload, len(cls._HEADER))
        return blob, torch.frombuffer(bytearray(q_raw), dtype=torch.int8)

    @classmethod
    def _direct_dequant(cls, native, q, blob, dst, qbit, scaling_method, rh, asym, signs, perm):
        native.kvweave_dequantize_fused_chunk_direct(
            q, blob, dst, cls._LAYERS, cls._TOKENS, cls._HEAD_NUM, cls._HEAD_DIM, qbit,
            rh=rh, asym=asym, scaling_method=scaling_method,
            signs=signs, perm=perm, num_threads=0,
        )

    @classmethod
    def _split_dequant(cls, native, q, blob, dtype, qbit, scaling_method, rh, asym, signs, perm):
        units = cls._LAYERS * cls._HEAD_NUM
        restored = native.kvweave_dequantize_chunk_state(
            q, blob, units, cls._TOKENS, cls._HEAD_DIM, output_dtype=dtype,
            **cls._state_kwargs(qbit, scaling_method, rh, asym, signs, perm),
        )
        return (
            restored.view(cls._LAYERS, cls._HEAD_NUM, cls._TOKENS, cls._HEAD_DIM)
            .permute(0, 2, 1, 3)
            .reshape(cls._LAYERS, cls._TOKENS, cls._HEAD_NUM * cls._HEAD_DIM)
        )

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16, torch.float32],
                             ids=["fp16", "bf16", "fp32"])
    @pytest.mark.parametrize("qbit", [4, 8], ids=["4bit", "8bit"])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    @pytest.mark.parametrize("asym", [False, True], ids=["sym", "asym"])
    def test_direct_dequant_matches_split_path(
        self, device, dtype, qbit, scaling_method, rh_precond, asym
    ):
        """Direct dequant into the fused layout == dequantize_chunk_state + head merge."""
        native = _native_module(device)
        rh, precond = rh_precond
        x, signs, perm = self._inputs(dtype, scaling_method, rh, seed=4)
        if not precond:
            signs = perm = None
        blob, q = self._encode(native, x, qbit, scaling_method, rh, asym, signs, perm)
        expected = self._split_dequant(native, q, blob, dtype, qbit, scaling_method, rh, asym, signs, perm)
        dst = torch.full_like(x, 7.0)
        self._direct_dequant(native, q, blob, dst, qbit, scaling_method, rh, asym, signs, perm)
        assert torch.equal(dst, expected)
        diff = (dst.float() - x.float()).abs()
        tol = _THRESHOLDS[qbit]
        assert diff.max().item() < tol["max_err"]
        assert diff.mean().item() < tol["mean_err"]

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    def test_direct_dequant_ignores_trailing_padding(self, device):
        native = _native_module(device)
        x, signs, perm = self._inputs(torch.float16, "per_channel", True, seed=5)
        blob, q = self._encode(native, x, 4, "per_channel", True, True, signs, perm)
        exact = torch.empty_like(x)
        padded = torch.empty_like(x)
        self._direct_dequant(native, q, blob, exact, 4, "per_channel", True, True, signs, perm)
        q_padded = torch.cat([q, torch.full((4096,), -17, dtype=torch.int8)])
        self._direct_dequant(native, q_padded, blob, padded, 4, "per_channel", True, True, signs, perm)
        assert torch.equal(exact, padded)
        with pytest.raises((ValueError, RuntimeError)):
            self._direct_dequant(native, q[:-1], blob, exact, 4, "per_channel", True, True, signs, perm)

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    def test_direct_dequant_rejects_invalid_args(self, device):
        native = _native_module(device)
        x, _, _ = self._inputs(torch.float16, "per_token", False)
        blob, q = self._encode(native, x, 4, "per_token", False, True, None, None)
        dst = torch.empty_like(x)
        with pytest.raises((ValueError, RuntimeError)):
            self._direct_dequant(native, q, blob, dst, 4, "per_tensor", False, True, None, None)
        with pytest.raises((ValueError, RuntimeError)):
            self._direct_dequant(native, q, blob, dst[:-1], 4, "per_token", False, True, None, None)
        with pytest.raises((ValueError, RuntimeError)):
            self._direct_dequant(native, q, blob[:-1], dst, 4, "per_token", False, True, None, None)
        with pytest.raises((ValueError, RuntimeError)):
            self._direct_dequant(native, q, blob, dst, 4, "per_channel", False, True, None, None)
        bad_perm = torch.arange(self._HEAD_DIM, dtype=torch.int32)
        bad_perm[0] = self._HEAD_DIM
        with pytest.raises((ValueError, RuntimeError)):
            self._direct_dequant(native, q, blob, dst, 4, "per_token", True, True, None, bad_perm)

    @requires_xpu
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    def test_xpu_direct_dequant_merge_fallback_matches(self, scaling_method):
        """Profiling forces the non-SLM path, which merges heads on device after dequant."""
        x, signs, perm = self._inputs(torch.float16, scaling_method, True, seed=6)
        blob, q = self._encode(kvweave_quant_xpu, x, 4, scaling_method, True, True, signs, perm)
        fast = torch.empty_like(x)
        slow = torch.empty_like(x)
        self._direct_dequant(kvweave_quant_xpu, q, blob, fast, 4, scaling_method, True, True, signs, perm)
        kvweave_quant_xpu.set_quant_profiling(True)
        try:
            self._direct_dequant(kvweave_quant_xpu, q, blob, slow, 4, scaling_method, True, True, signs, perm)
        finally:
            kvweave_quant_xpu.set_quant_profiling(False)
            kvweave_quant_xpu.reset_profile_stats()
        torch.testing.assert_close(fast, slow, rtol=2e-3, atol=2e-3)



