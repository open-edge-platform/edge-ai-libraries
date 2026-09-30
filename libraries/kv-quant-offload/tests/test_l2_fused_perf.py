# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""L2 performance benchmarks for the fused serialize/dequantize chunk API.

Production-shaped CPU benchmarks for the LMCache replay hot path, swept across
thread counts. The former "with_layout_prep"/"with_layout_restore" variants
(which timed the 3D<->4D reshape alongside the kernel) were removed; layout
handling is exercised at L3 via the codec's own perf tests.
"""
from __future__ import annotations

import pytest
import torch

from kvweave import kvweave_quant
from conftest import (
    PROD_CHUNK_TOKENS,
    PROD_HEAD_DIM,
    PROD_NUM_KV_HEADS,
    build_quant_cfg,
    bench,
    generate_chunk,
    prepare_fused_inputs,
    print_bench_result,
    split_kvw2_payload,
)


_PROD_PERF_THREADS = [1, 2, 4, 8, 16]


@pytest.mark.perf
class TestL2FusedThreadSweep:
    """Fused kvweave_serialize_chunk / kvweave_dequantize_chunk across threads."""

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_serialize_chunk_threads(self, num_threads, perf_collector):
        """Measure fused CPU quantize+pack without source layout prep."""
        cfg = build_quant_cfg(
            qbit=4,
            scaling_method="per_channel",
            rh=True,
            asym=True,
            precond=True,
            chunk_tokens=PROD_CHUNK_TOKENS,
            head_num=PROD_NUM_KV_HEADS,
            head_dim=PROD_HEAD_DIM,
            num_threads=num_threads,
        )
        chunk = generate_chunk(
            chunk_tokens=PROD_CHUNK_TOKENS,
            head_num=PROD_NUM_KV_HEADS,
            head_dim=PROD_HEAD_DIM,
            dtype=torch.float16,
            seed=7,
        )
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)
        data_bytes = tensor_4d.numel() * tensor_4d.element_size()

        def _fn():
            kvweave_quant.kvweave_serialize_chunk(
                tensor_4d,
                header,
                0xF0F0,
                0xF0F1,
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
            )

        result = bench(
            _fn,
            warmup=5,
            iters=100,
            data_bytes=data_bytes,
            stage=f"l2_fused_serialize_threads_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_dequantize_chunk_threads(self, num_threads, perf_collector):
        """Measure fused CPU dequant for the current LMCache replay shape."""
        cfg = build_quant_cfg(
            qbit=4,
            scaling_method="per_channel",
            rh=True,
            asym=True,
            precond=True,
            chunk_tokens=PROD_CHUNK_TOKENS,
            head_num=PROD_NUM_KV_HEADS,
            head_dim=PROD_HEAD_DIM,
            num_threads=num_threads,
        )
        chunk = generate_chunk(
            chunk_tokens=PROD_CHUNK_TOKENS,
            head_num=PROD_NUM_KV_HEADS,
            head_dim=PROD_HEAD_DIM,
            dtype=torch.float16,
            seed=11,
        )
        tensor_4d, header = prepare_fused_inputs(chunk, cfg)
        payload = bytes(
            kvweave_quant.kvweave_serialize_chunk(
                tensor_4d,
                header,
                0xF200,
                0xF201,
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
            )
        )
        scale_blobs, q_raw = split_kvw2_payload(payload)
        q_data = torch.frombuffer(bytearray(q_raw), dtype=torch.int8)
        h_merged = PROD_NUM_KV_HEADS * PROD_HEAD_DIM
        data_bytes = q_data.numel() * q_data.element_size()

        def _fn():
            kvweave_quant.kvweave_dequantize_chunk(
                q_data,
                scale_blobs[0],
                scale_blobs[1],
                1,
                PROD_CHUNK_TOKENS,
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

        result = bench(
            _fn,
            warmup=5,
            iters=100,
            data_bytes=data_bytes,
            stage=f"l2_fused_dequantize_threads_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)
