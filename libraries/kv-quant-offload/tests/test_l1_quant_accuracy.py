# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Quantize/dequantize roundtrip accuracy tests.

Each test outputs concrete error values (max_err, mean_err) to stdout,
with loose assert thresholds as regression protection.

Note: quantize_kvcache operates on ONE HALF (K or V), not the full KV tensor.
The input tensor size must be blocks_num * block_size * head_num * head_dim.
"""
from __future__ import annotations

import struct

import pytest
import torch

from kvweave import kvweave_quant
from conftest import (
    PROD_BLOCK_SIZE,
    PROD_CHUNK_TOKENS,
    PROD_HEAD_DIM,
    PROD_NUM_KV_HEADS,
    build_quant_cfg,
    generate_chunk,
    generate_preconditioning,
    quant_dequant_roundtrip,
    quant_dequant_roundtrip_xpu,
    requires_xpu,
)

try:
    from kvweave import kvweave_quant_xpu
except ImportError:
    kvweave_quant_xpu = None

# Regression thresholds (intentionally loose — the printed values are what matters)
_THRESHOLDS = {
    4: {"max_err": 0.20, "mean_err": 0.05},
    8: {"max_err": 0.05, "mean_err": 0.01},
}


def _generate_half_tensor(
    cfg: dict, dtype: torch.dtype = torch.float16, seed: int = 0
) -> torch.Tensor:
    """Generate a flat tensor for one K or V half (blocks_num * block_size * head_num * head_dim)."""
    element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
    g = torch.Generator().manual_seed(seed)
    t = torch.randn(element_count, generator=g, dtype=torch.float32) * 0.05
    t = t.clamp(-0.3, 0.3)
    return t.to(dtype)


class TestL1QuantRoundtrip:
    """Quantize → dequantize roundtrip accuracy across all mode combinations."""

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    @pytest.mark.parametrize("asym", [False, True], ids=["sym", "asym"])
    def test_roundtrip_fp16(self, qbit, scaling_method, rh_precond, asym):
        """Roundtrip accuracy for fp16 input."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=asym, precond=precond,
        )
        src = _generate_half_tensor(cfg, dtype=torch.float16)

        _, restored = quant_dequant_roundtrip(src, cfg)

        diff = (restored.float() - src.float()).abs()
        max_err = diff.max().item()
        mean_err = diff.mean().item()

        print(
            f"ACC | qbit={qbit} scaling={scaling_method} "
            f"rh={rh} precond={precond} asym={asym} dtype=fp16 | "
            f"max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )

        tol = _THRESHOLDS[qbit]
        assert max_err < tol["max_err"], f"max_err={max_err} exceeds {tol['max_err']}"
        assert mean_err < tol["mean_err"], f"mean_err={mean_err} exceeds {tol['mean_err']}"

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    @pytest.mark.parametrize("asym", [False, True], ids=["sym", "asym"])
    def test_roundtrip_bf16(self, qbit, scaling_method, rh_precond, asym):
        """Roundtrip accuracy for bf16 input."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=asym, precond=precond,
        )
        src = _generate_half_tensor(cfg, dtype=torch.bfloat16)

        _, restored = quant_dequant_roundtrip(src, cfg)

        diff = (restored.float() - src.float()).abs()
        max_err = diff.max().item()
        mean_err = diff.mean().item()

        print(
            f"ACC | qbit={qbit} scaling={scaling_method} "
            f"rh={rh} precond={precond} asym={asym} dtype=bf16 | "
            f"max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )

        tol = _THRESHOLDS[qbit]
        assert max_err < tol["max_err"], f"max_err={max_err} exceeds {tol['max_err']}"
        assert mean_err < tol["mean_err"], f"mean_err={mean_err} exceeds {tol['mean_err']}"

    def test_zero_tensor_roundtrip(self):
        """All-zero input produces all-zero (or near-zero) output."""
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        src = torch.zeros(element_count, dtype=torch.float16)

        _, restored = quant_dequant_roundtrip(src, cfg)

        max_err = restored.abs().max().item()
        print(f"ACC | zero_tensor qbit=8 | max_err={max_err:.6f}")
        assert max_err < 1e-6

    @pytest.mark.parametrize("blocks_num", [1, 4, 8], ids=["1block", "4blocks", "8blocks"])
    def test_multiple_blocks(self, blocks_num):
        """Verify accuracy across different block counts."""
        chunk_tokens = blocks_num * PROD_BLOCK_SIZE
        cfg = build_quant_cfg(
            qbit=4, scaling_method="per_channel",
            rh=True, asym=True, precond=True,
            chunk_tokens=chunk_tokens, blocks_num=blocks_num,
        )
        src = _generate_half_tensor(cfg, dtype=torch.float16)

        _, restored = quant_dequant_roundtrip(src, cfg)

        diff = (restored.float() - src.float()).abs()
        max_err = diff.max().item()
        mean_err = diff.mean().item()
        print(
            f"ACC | blocks_num={blocks_num} chunk_tokens={chunk_tokens} | "
            f"max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )
        assert max_err < _THRESHOLDS[4]["max_err"]


class TestL1ScaleLifecycle:
    """Verify scale lifecycle: get/set/clear operations."""

    def test_get_scales_after_quantize(self):
        """get_scales_for_id returns non-empty bytes after quantize."""
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        src = _generate_half_tensor(cfg, dtype=torch.float16)
        scale_id = 0x5000

        kvweave_quant.quantize_kvcache(
            src,
            scale_id=scale_id,
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
        )
        scales = kvweave_quant.get_scales_for_id(scale_id)
        assert len(scales) > 0, "scales should be non-empty after quantize"
        kvweave_quant.clear_scales_for_id(scale_id)

    def test_clear_scales(self):
        """After clear, get_scales_for_id returns empty bytes."""
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        src = _generate_half_tensor(cfg, dtype=torch.float16)
        scale_id = 0x5100

        kvweave_quant.quantize_kvcache(
            src,
            scale_id=scale_id,
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
        )
        kvweave_quant.clear_scales_for_id(scale_id)
        scales = kvweave_quant.get_scales_for_id(scale_id)
        # After clear, the scale blob is either empty or a 4-byte header with count=0
        import struct
        if len(scales) > 0:
            count = struct.unpack_from(">I", scales, 0)[0] if len(scales) >= 4 else -1
            assert count == 0, f"scales count should be 0 after clear, got {count}"

    def test_set_then_dequantize(self):
        """set_scales_for_id restores scales for correct dequantization."""
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        src = _generate_half_tensor(cfg, dtype=torch.float16)
        q_id = 0x5200
        dq_id = 0x5201

        quantized = kvweave_quant.quantize_kvcache(
            src,
            scale_id=q_id,
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
        )
        scales_bytes = kvweave_quant.get_scales_for_id(q_id)
        kvweave_quant.clear_scales_for_id(q_id)

        kvweave_quant.set_scales_for_id(dq_id, scales_bytes)
        restored = kvweave_quant.dequantize_kvcache(
            quantized,
            scale_id=dq_id,
            qbit=cfg["qbit"],
            blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"],
            head_num=cfg["head_num"],
            head_dim=cfg["head_dim"],
            rh=cfg["rh"],
            asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            output_dtype=torch.float16,
            signs=None,
            perm=None,
            num_threads=cfg["num_threads"],
        )
        kvweave_quant.clear_scales_for_id(dq_id)

        diff = (restored.float() - src.float()).abs()
        max_err = diff.max().item()
        print(f"ACC | set_then_dequant | max_err={max_err:.6f}")
        assert max_err < _THRESHOLDS[8]["max_err"]

    def test_scale_ids_independent(self):
        """Different scale_ids produce separate scale entries."""
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        src1 = _generate_half_tensor(cfg, dtype=torch.float16, seed=1)
        src2 = _generate_half_tensor(cfg, dtype=torch.float16, seed=2)
        id1, id2 = 0x6000, 0x6001

        kvweave_quant.quantize_kvcache(
            src1, scale_id=id1, qbit=cfg["qbit"],
            blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"],
            rh=cfg["rh"], asym=cfg["asym"], scaling_method=cfg["scaling_method"],
            signs=None, perm=None, num_threads=cfg["num_threads"],
        )
        kvweave_quant.quantize_kvcache(
            src2, scale_id=id2, qbit=cfg["qbit"],
            blocks_num=cfg["blocks_num"], block_size=cfg["block_size"],
            head_num=cfg["head_num"], head_dim=cfg["head_dim"],
            rh=cfg["rh"], asym=cfg["asym"], scaling_method=cfg["scaling_method"],
            signs=None, perm=None, num_threads=cfg["num_threads"],
        )

        s1 = kvweave_quant.get_scales_for_id(id1)
        s2 = kvweave_quant.get_scales_for_id(id2)
        assert s1 != s2, "different inputs should produce different scales"
        kvweave_quant.clear_scales_for_id(id1)
        kvweave_quant.clear_scales_for_id(id2)


@requires_xpu
class TestL1QuantRoundtripXPU:
    """XPU (SYCL) roundtrip accuracy, mirroring TestL1QuantRoundtrip via kvweave_quant_xpu (no scale_id table or thread sweep)."""

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    @pytest.mark.parametrize("asym", [False, True], ids=["sym", "asym"])
    def test_roundtrip_fp16(self, qbit, scaling_method, rh_precond, asym):
        """Roundtrip accuracy for fp16 input."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=asym, precond=precond,
        )
        src = _generate_half_tensor(cfg, dtype=torch.float16)

        _, restored = quant_dequant_roundtrip_xpu(src, cfg)

        diff = (restored.float().cpu() - src.float()).abs()
        max_err = diff.max().item()
        mean_err = diff.mean().item()

        print(
            f"ACC | xpu qbit={qbit} scaling={scaling_method} "
            f"rh={rh} precond={precond} asym={asym} dtype=fp16 | "
            f"max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )

        tol = _THRESHOLDS[qbit]
        assert max_err < tol["max_err"], f"max_err={max_err} exceeds {tol['max_err']}"
        assert mean_err < tol["mean_err"], f"mean_err={mean_err} exceeds {tol['mean_err']}"

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    @pytest.mark.parametrize("asym", [False, True], ids=["sym", "asym"])
    def test_roundtrip_bf16(self, qbit, scaling_method, rh_precond, asym):
        """Roundtrip accuracy for bf16 input."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=asym, precond=precond,
        )
        src = _generate_half_tensor(cfg, dtype=torch.bfloat16)

        _, restored = quant_dequant_roundtrip_xpu(src, cfg)

        diff = (restored.float().cpu() - src.float()).abs()
        max_err = diff.max().item()
        mean_err = diff.mean().item()

        print(
            f"ACC | xpu qbit={qbit} scaling={scaling_method} "
            f"rh={rh} precond={precond} asym={asym} dtype=bf16 | "
            f"max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )

        tol = _THRESHOLDS[qbit]
        assert max_err < tol["max_err"], f"max_err={max_err} exceeds {tol['max_err']}"
        assert mean_err < tol["mean_err"], f"mean_err={mean_err} exceeds {tol['mean_err']}"

    def test_zero_tensor_roundtrip(self):
        """All-zero input produces all-zero (or near-zero) output."""
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        src = torch.zeros(element_count, dtype=torch.float16)

        _, restored = quant_dequant_roundtrip_xpu(src, cfg)

        max_err = restored.cpu().abs().max().item()
        print(f"ACC | xpu zero_tensor qbit=8 | max_err={max_err:.6f}")
        assert max_err < 1e-6

    @pytest.mark.parametrize("blocks_num", [1, 4, 8], ids=["1block", "4blocks", "8blocks"])
    def test_multiple_blocks(self, blocks_num):
        """Verify accuracy across different block counts."""
        chunk_tokens = blocks_num * PROD_BLOCK_SIZE
        cfg = build_quant_cfg(
            qbit=4, scaling_method="per_channel",
            rh=True, asym=True, precond=True,
            chunk_tokens=chunk_tokens, blocks_num=blocks_num,
        )
        src = _generate_half_tensor(cfg, dtype=torch.float16)

        _, restored = quant_dequant_roundtrip_xpu(src, cfg)

        diff = (restored.float().cpu() - src.float()).abs()
        max_err = diff.max().item()
        mean_err = diff.mean().item()
        print(
            f"ACC | xpu blocks_num={blocks_num} chunk_tokens={chunk_tokens} | "
            f"max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )
        assert max_err < _THRESHOLDS[4]["max_err"]


def _parse_scale_entries(blob: bytes) -> torch.Tensor:
    """One count-prefixed scale segment -> [count, 2] (scale, zp)."""
    (count,) = struct.unpack_from("<I", blob, 0)
    out = torch.empty(count, 2, dtype=torch.float32)
    for k in range(count):
        idx, scale, zp = struct.unpack_from("<Iff", blob, 4 + 12 * k)
        assert idx < count
        out[idx, 0], out[idx, 1] = scale, zp
    return out


class TestL1FusedDirectQuant:
    """kvweave_serialize_fused_chunk_direct vs per-(layer, head) quantize_kvcache.

    Production geometry: each unit's tokens x head_dim slice of the fused
    [layers, tokens, 2*kv_heads*head_dim] tensor must quantize exactly as the
    single-plane kernel does on that slice.
    """

    _LAYERS = 2
    _HEAD_NUM = 2 * PROD_NUM_KV_HEADS

    @staticmethod
    def _quant_unit(device, unit_src, qbit, scaling_method, rh, signs, perm):
        tokens = unit_src.shape[0]
        if device == "cpu":
            scale_id = 0x7F00
            q = kvweave_quant.quantize_kvcache(
                unit_src.reshape(-1), scale_id=scale_id, qbit=qbit,
                blocks_num=1, block_size=tokens, head_num=1, head_dim=PROD_HEAD_DIM,
                rh=rh, asym=True, scaling_method=scaling_method,
                signs=signs, perm=perm, num_threads=0,
            )
            scales = kvweave_quant.get_scales_for_id(scale_id)
            kvweave_quant.clear_scales_for_id(scale_id)
            return q.view(torch.uint8).reshape(-1), scales
        q, scales = kvweave_quant_xpu.quantize_kvcache(
            unit_src.reshape(-1).to("xpu"), qbit, 1, tokens, 1, PROD_HEAD_DIM,
            rh, True, scaling_method, signs, perm,
        )
        return q.cpu().view(torch.uint8).reshape(-1), scales

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("qbit", [4, 8], ids=["4bit", "8bit"])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    @pytest.mark.parametrize("rh", [False, True], ids=["no_rh", "rh"])
    def test_direct_matches_per_unit_quantize(self, device, qbit, scaling_method, rh):
        native = kvweave_quant if device == "cpu" else kvweave_quant_xpu
        tokens = PROD_CHUNK_TOKENS
        hidden = self._HEAD_NUM * PROD_HEAD_DIM
        g = torch.Generator().manual_seed(11)
        x = (torch.randn(self._LAYERS, tokens, hidden, generator=g) * 0.05).to(torch.float16)
        signs = perm = None
        if rh:
            n = tokens if scaling_method == "per_channel" else PROD_HEAD_DIM
            signs, perm = generate_preconditioning(n)

        header = b"L1FD"
        payload = bytes(native.kvweave_serialize_fused_chunk_direct(
            x, header, qbit, self._HEAD_NUM, PROD_HEAD_DIM,
            rh=rh, asym=True, scaling_method=scaling_method,
            signs=signs, perm=perm, num_threads=0,
        ))
        off = len(header)
        (scale_len,) = struct.unpack_from(">I", payload, off)
        off += 4
        blob, q_all = payload[off:off + scale_len], payload[off + scale_len:]
        q_all = torch.frombuffer(bytearray(q_all), dtype=torch.uint8)

        units = self._LAYERS * self._HEAD_NUM
        unit_q = q_all.numel() // units
        seg = len(blob) // units
        split = x.reshape(self._LAYERS, tokens, self._HEAD_NUM, PROD_HEAD_DIM).permute(0, 2, 1, 3)
        worst_mismatch = 0.0
        for u in range(units):
            ref_q, ref_scales = self._quant_unit(
                device, split[u // self._HEAD_NUM, u % self._HEAD_NUM].contiguous(),
                qbit, scaling_method, rh, signs, perm,
            )
            assert ref_q.numel() == unit_q
            # ~1 ulp drift allowed: default builds use a fast fp-model.
            torch.testing.assert_close(
                _parse_scale_entries(blob[u * seg:(u + 1) * seg]),
                _parse_scale_entries(ref_scales), rtol=1e-5, atol=1e-6)
            got = q_all[u * unit_q:(u + 1) * unit_q]
            worst_mismatch = max(worst_mismatch, (got != ref_q).float().mean().item())
        print(f"ACC | fused_direct device={device} qbit={qbit} scaling={scaling_method} "
              f"rh={rh} | worst_q_mismatch={worst_mismatch:.6f}")
        assert worst_mismatch < 1e-2

    @pytest.mark.parametrize("device", ["cpu", pytest.param("xpu", marks=requires_xpu)])
    @pytest.mark.parametrize("qbit", [4, 8], ids=["4bit", "8bit"])
    @pytest.mark.parametrize("scaling_method", ["per_token", "per_channel"])
    @pytest.mark.parametrize("rh", [False, True], ids=["no_rh", "rh"])
    def test_direct_dequant_matches_per_unit_dequant(self, device, qbit, scaling_method, rh):
        """kvweave_dequantize_fused_chunk_direct vs per-unit dequant + head merge,
        at production geometry."""
        native = kvweave_quant if device == "cpu" else kvweave_quant_xpu
        tokens = PROD_CHUNK_TOKENS
        hidden = self._HEAD_NUM * PROD_HEAD_DIM
        g = torch.Generator().manual_seed(12)
        x = (torch.randn(self._LAYERS, tokens, hidden, generator=g) * 0.05).to(torch.float16)
        signs = perm = None
        if rh:
            signs, perm = generate_preconditioning(
                tokens if scaling_method == "per_channel" else PROD_HEAD_DIM)

        header = b"L1FD"
        payload = bytes(native.kvweave_serialize_fused_chunk_direct(
            x, header, qbit, self._HEAD_NUM, PROD_HEAD_DIM,
            rh=rh, asym=True, scaling_method=scaling_method,
            signs=signs, perm=perm, num_threads=0,
        ))
        off = len(header)
        (scale_len,) = struct.unpack_from(">I", payload, off)
        off += 4
        blob = payload[off:off + scale_len]
        q = torch.frombuffer(bytearray(payload[off + scale_len:]), dtype=torch.int8)

        units = self._LAYERS * self._HEAD_NUM
        restored = native.kvweave_dequantize_chunk_state(
            q, blob, units, tokens, PROD_HEAD_DIM, qbit=qbit, blocks_num=1,
            block_size=tokens, head_num=self._HEAD_NUM, head_dim=PROD_HEAD_DIM,
            rh=rh, asym=True, scaling_method=scaling_method,
            output_dtype=torch.float16, signs=signs, perm=perm, num_threads=0,
        )
        expected = (
            restored.view(self._LAYERS, self._HEAD_NUM, tokens, PROD_HEAD_DIM)
            .permute(0, 2, 1, 3)
            .reshape_as(x)
        )
        dst = torch.empty_like(x)
        native.kvweave_dequantize_fused_chunk_direct(
            q, blob, dst, self._LAYERS, tokens, self._HEAD_NUM, PROD_HEAD_DIM, qbit,
            rh=rh, asym=True, scaling_method=scaling_method,
            signs=signs, perm=perm, num_threads=0,
        )
        assert torch.equal(dst, expected)
        diff = (dst.float() - x.float()).abs()
        print(f"ACC | fused_direct_dequant device={device} qbit={qbit} scaling={scaling_method} "
              f"rh={rh} | max_err={diff.max().item():.6f} mean_err={diff.mean().item():.6f}")
        assert diff.max().item() < _THRESHOLDS[qbit]["max_err"]
        assert diff.mean().item() < _THRESHOLDS[qbit]["mean_err"]
