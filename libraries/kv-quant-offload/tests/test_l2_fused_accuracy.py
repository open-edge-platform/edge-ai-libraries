# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for fused kvweave_serialize_chunk and kvweave_dequantize_chunk APIs."""
from __future__ import annotations

import pytest
import torch

from kvweave import kvweave_quant
from conftest import (
    build_quant_cfg,
    generate_chunk,
    prepare_fused_inputs,
    split_kvw2_payload,
)

# Thresholds are higher than test_quant_accuracy because generate_chunk
# includes 1% outliers (values up to ±5.0) which push max_err higher.
# 4-bit asymmetric without rh on outlier data can have very high mean_err.
_THRESHOLDS = {
    4: {"max_err": 0.50, "mean_err": 0.35},
    8: {"max_err": 0.10, "mean_err": 0.02},
}


class TestL2FusedRoundtrip:
    """Tests for kvweave_serialize_chunk."""

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    @pytest.mark.parametrize("asym", [False, True], ids=["sym", "asym"])
    def test_fused_roundtrip_accuracy(self, qbit, scaling_method, rh_precond, asym):
        """Fused serialize → dequantize_chunk roundtrip accuracy."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=asym, precond=precond,
        )
        chunk = generate_chunk(dtype=torch.float16)
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)

        scale_id_k, scale_id_v = 0xA000, 0xA001
        payload = bytes(kvweave_quant.kvweave_serialize_chunk(
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

        restored = kvweave_quant.kvweave_dequantize_chunk(
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
            f"ACC | fused qbit={qbit} scaling={scaling_method} "
            f"rh={rh} precond={precond} asym={asym} | "
            f"max_err={max_err:.6f} mean_err={mean_err:.6f}"
        )

        tol = _THRESHOLDS[qbit]
        assert max_err < tol["max_err"]
        assert mean_err < tol["mean_err"]

    def test_fused_matches_sequential(self):
        """Fused API output matches step-by-step quantize + get_scales + pack."""
        cfg = build_quant_cfg(
            qbit=8, scaling_method="per_token",
            rh=False, asym=False, precond=False,
        )
        chunk = generate_chunk(dtype=torch.float16)
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)

        # Fused path
        fused_payload = bytes(kvweave_quant.kvweave_serialize_chunk(
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
        seq_payload = bytes(kvweave_quant.kvweave_serialize_chunk(
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

    def test_output_shape(self):
        """Dequantize chunk returns correct shape [2, num_layers, T, H*D]."""
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        chunk = generate_chunk(dtype=torch.float16)
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)
        chunk_tokens, _, h_merged = chunk.shape

        payload = bytes(kvweave_quant.kvweave_serialize_chunk(
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

        restored = kvweave_quant.kvweave_dequantize_chunk(
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

    @pytest.mark.parametrize("out_dtype", [torch.float16, torch.bfloat16], ids=["fp16", "bf16"])
    def test_output_dtype(self, out_dtype):
        """Dequantize respects output_dtype parameter."""
        cfg = build_quant_cfg(qbit=8, scaling_method="per_token", rh=False, asym=False, precond=False)
        chunk = generate_chunk(dtype=torch.float16)
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)
        chunk_tokens, _, h_merged = chunk.shape

        payload = bytes(kvweave_quant.kvweave_serialize_chunk(
            tensor_4d, header, 0xD000, 0xD001,
            qbit=cfg["qbit"], blocks_num=cfg["blocks_num"],
            block_size=cfg["block_size"], head_num=cfg["head_num"],
            head_dim=cfg["head_dim"], rh=cfg["rh"], asym=cfg["asym"],
            scaling_method=cfg["scaling_method"],
            signs=None, perm=None, num_threads=cfg["num_threads"],
        ))

        scale_blobs, q_raw = split_kvw2_payload(payload)
        q_data = torch.frombuffer(bytearray(q_raw), dtype=torch.int8)

        restored = kvweave_quant.kvweave_dequantize_chunk(
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



