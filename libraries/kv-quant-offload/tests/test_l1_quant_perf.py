# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""L1 performance benchmarks for the low-level quantize/dequantize kernels.

Two orthogonal axes:
- TestL1QuantConfigSweep: scaling_method x rh_precond at num_threads=1 —
  "which quant mode is fastest" signal.
- TestL1QuantThreadSweep: fixed production config across thread counts —
  "how the kernel scales with threads" signal.
"""
from __future__ import annotations

import itertools

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
    print_bench_result,
    requires_xpu,
)

try:
    from kvweave import kvweave_quant_xpu
except ImportError:
    kvweave_quant_xpu = None


_PROD_PERF_THREADS = [1, 2, 4, 8, 16]

# Rotate through distinct buffers so the GPU L2 stays cold, as in serving.
_XPU_SRC_POOL_SIZE = 64


@pytest.mark.perf
class TestL1QuantConfigSweep:
    """Quantize/dequantize throughput across scaling x rh_precond at t1."""

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    def test_quantize_throughput(self, qbit, scaling_method, rh_precond, perf_collector):
        """Measure quantize throughput in GB/s."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=True, precond=precond,
        )
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        src = torch.randn(element_count, dtype=torch.float32).clamp(-0.3, 0.3).to(torch.float16)
        data_bytes = src.numel() * src.element_size()
        scale_id = 0x8000

        def _fn():
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
                signs=cfg["signs"],
                perm=cfg["perm"],
                num_threads=cfg["num_threads"],
            )
            kvweave_quant.clear_scales_for_id(scale_id)

        result = bench(_fn, warmup=5, iters=1000, data_bytes=data_bytes,
                       stage=f"l1_quantize_config_q{qbit}_{scaling_method}_rh{rh}_pc{precond}")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    def test_dequantize_throughput(self, qbit, scaling_method, rh_precond, perf_collector):
        """Measure dequantize throughput in GB/s."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=True, precond=precond,
        )
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        src = torch.randn(element_count, dtype=torch.float32).clamp(-0.3, 0.3).to(torch.float16)
        scale_id = 0x8100

        # Pre-quantize to get quantized data + scales
        quantized = kvweave_quant.quantize_kvcache(
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
            signs=cfg["signs"],
            perm=cfg["perm"],
            num_threads=cfg["num_threads"],
        )
        scales_bytes = kvweave_quant.get_scales_for_id(scale_id)
        kvweave_quant.clear_scales_for_id(scale_id)

        data_bytes = quantized.numel() * quantized.element_size()
        dq_id = 0x8200

        def _fn():
            kvweave_quant.set_scales_for_id(dq_id, scales_bytes)
            kvweave_quant.dequantize_kvcache(
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
                signs=cfg["signs"],
                perm=cfg["perm"],
                num_threads=cfg["num_threads"],
            )
            kvweave_quant.clear_scales_for_id(dq_id)

        result = bench(_fn, warmup=5, iters=1000, data_bytes=data_bytes,
                       stage=f"l1_dequantize_config_q{qbit}_{scaling_method}_rh{rh}_pc{precond}")
        print_bench_result(result)
        perf_collector.append(result)


@pytest.mark.perf
class TestL1QuantThreadSweep:
    """Production-config kernel-only benchmarks across thread counts."""

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_quantize_threads(self, num_threads, perf_collector):
        """Measure raw quantize kernel throughput for the production config."""
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
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        src = generate_chunk(
            chunk_tokens=PROD_CHUNK_TOKENS,
            head_num=PROD_NUM_KV_HEADS,
            head_dim=PROD_HEAD_DIM,
            dtype=torch.float16,
            seed=101,
        )[:, 0, :].reshape(element_count)
        data_bytes = src.numel() * src.element_size()
        scale_id = 0x9100 + num_threads

        def _fn():
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
                signs=cfg["signs"],
                perm=cfg["perm"],
                num_threads=cfg["num_threads"],
            )
            kvweave_quant.clear_scales_for_id(scale_id)

        result = bench(
            _fn,
            warmup=5,
            iters=1000,
            data_bytes=data_bytes,
            stage=f"l1_quantize_threads_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_dequantize_threads(self, num_threads, perf_collector):
        """Measure raw dequantize kernel throughput for the production config."""
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
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        src = generate_chunk(
            chunk_tokens=PROD_CHUNK_TOKENS,
            head_num=PROD_NUM_KV_HEADS,
            head_dim=PROD_HEAD_DIM,
            dtype=torch.float16,
            seed=102,
        )[:, 0, :].reshape(element_count)
        scale_id = 0x9200 + num_threads
        quantized = kvweave_quant.quantize_kvcache(
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
            signs=cfg["signs"],
            perm=cfg["perm"],
            num_threads=cfg["num_threads"],
        )
        scales_bytes = kvweave_quant.get_scales_for_id(scale_id)
        kvweave_quant.clear_scales_for_id(scale_id)
        data_bytes = quantized.numel() * quantized.element_size()
        dq_id = 0x9300 + num_threads

        def _fn():
            kvweave_quant.set_scales_for_id(dq_id, scales_bytes)
            kvweave_quant.dequantize_kvcache(
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
                signs=cfg["signs"],
                perm=cfg["perm"],
                num_threads=cfg["num_threads"],
            )
            kvweave_quant.clear_scales_for_id(dq_id)

        result = bench(
            _fn,
            warmup=5,
            iters=1000,
            data_bytes=data_bytes,
            stage=f"l1_dequantize_threads_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)


@requires_xpu
@pytest.mark.perf
class TestL1QuantConfigSweepXPU:
    """XPU quantize/dequantize throughput across scaling x rh_precond (no thread sweep)."""

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    def test_quantize_throughput(self, qbit, scaling_method, rh_precond, perf_collector):
        """Measure quantize throughput in GB/s."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=True, precond=precond,
        )
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        srcs = [
            torch.randn(element_count, dtype=torch.float32).clamp(-0.3, 0.3).to(torch.float16).to("xpu")
            for _ in range(_XPU_SRC_POOL_SIZE)
        ]
        data_bytes = srcs[0].numel() * srcs[0].element_size()
        src_cycle = itertools.cycle(srcs)

        def _fn():
            kvweave_quant_xpu.quantize_kvcache(
                next(src_cycle),
                cfg["qbit"],
                cfg["blocks_num"],
                cfg["block_size"],
                cfg["head_num"],
                cfg["head_dim"],
                cfg["rh"],
                cfg["asym"],
                cfg["scaling_method"],
                cfg["signs"],
                cfg["perm"],
            )

        result = bench(_fn, warmup=5, iters=1000, data_bytes=data_bytes,
                       stage=f"l1_quantize_config_q{qbit}_{scaling_method}_rh{rh}_pc{precond}_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("qbit", [4], ids=["4bit"])
    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    def test_dequantize_throughput(self, qbit, scaling_method, rh_precond, perf_collector):
        """Measure dequantize throughput in GB/s."""
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=qbit, scaling_method=scaling_method,
            rh=rh, asym=True, precond=precond,
        )
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]

        # Pre-quantize a pool of distinct chunks to get quantized data + scales.
        pool = []
        for _ in range(_XPU_SRC_POOL_SIZE):
            src = torch.randn(element_count, dtype=torch.float32).clamp(-0.3, 0.3).to(torch.float16).to("xpu")
            quantized, scale_bytes = kvweave_quant_xpu.quantize_kvcache(
                src,
                cfg["qbit"],
                cfg["blocks_num"],
                cfg["block_size"],
                cfg["head_num"],
                cfg["head_dim"],
                cfg["rh"],
                cfg["asym"],
                cfg["scaling_method"],
                cfg["signs"],
                cfg["perm"],
            )
            pool.append((quantized, scale_bytes))
        data_bytes = pool[0][0].numel() * pool[0][0].element_size()
        pool_cycle = itertools.cycle(pool)

        def _fn():
            quantized, scale_bytes = next(pool_cycle)
            kvweave_quant_xpu.dequantize_kvcache(
                quantized,
                scale_bytes,
                cfg["qbit"],
                cfg["blocks_num"],
                cfg["block_size"],
                cfg["head_num"],
                cfg["head_dim"],
                cfg["rh"],
                cfg["asym"],
                cfg["scaling_method"],
                torch.float16,
                cfg["signs"],
                cfg["perm"],
            )

        result = bench(_fn, warmup=5, iters=1000, data_bytes=data_bytes,
                       stage=f"l1_dequantize_config_q{qbit}_{scaling_method}_rh{rh}_pc{precond}_xpu")
        print_bench_result(result)
        perf_collector.append(result)


def _print_stage_breakdown(label, stats, stage_names):
    print(f"PERF | {label}")
    for stage in stage_names:
        s = stats[stage]
        print(f"  {stage:<16} total={s['total_ms']:.3f}ms  calls={s['calls']}  pct={s['pct']:.1f}%")


_QUANTIZE_STAGES = ["LoadGather", "Hadamard", "ReduceQuantize", "Pack4bit"]
_DEQUANTIZE_STAGES = ["Unpack4bit", "DequantLoad", "HadamardInverse", "PrecondWriteback"]


@requires_xpu
@pytest.mark.perf
class TestL1QuantProfileBreakdownXPU:
    """Per-stage time breakdown inside the SYCL kernel. Profiling forces the multi-kernel path, so only the relative percentages are meaningful."""

    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    def test_quantize_stage_breakdown(self, scaling_method, rh_precond):
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=4, scaling_method=scaling_method,
            rh=rh, asym=True, precond=precond,
        )
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        src = torch.randn(element_count, dtype=torch.float32).clamp(-0.3, 0.3).to(torch.float16).to("xpu")

        kvweave_quant_xpu.reset_profile_stats()
        kvweave_quant_xpu.set_quant_profiling(True)
        try:
            for _ in range(50):
                kvweave_quant_xpu.quantize_kvcache(
                    src,
                    cfg["qbit"],
                    cfg["blocks_num"],
                    cfg["block_size"],
                    cfg["head_num"],
                    cfg["head_dim"],
                    cfg["rh"],
                    cfg["asym"],
                    cfg["scaling_method"],
                    cfg["signs"],
                    cfg["perm"],
                )
        finally:
            kvweave_quant_xpu.set_quant_profiling(False)

        stats = kvweave_quant_xpu.get_profile_stats()
        _print_stage_breakdown(
            f"quantize_stage_breakdown_{scaling_method}_rh{rh}_pc{precond}",
            stats, _QUANTIZE_STAGES)

    @pytest.mark.parametrize("scaling_method", ["per_tensor", "per_token", "per_channel"])
    @pytest.mark.parametrize("rh_precond", [(False, False), (True, False), (True, True)],
                             ids=["no_rh", "rh_no_precond", "rh_precond"])
    def test_dequantize_stage_breakdown(self, scaling_method, rh_precond):
        rh, precond = rh_precond
        cfg = build_quant_cfg(
            qbit=4, scaling_method=scaling_method,
            rh=rh, asym=True, precond=precond,
        )
        element_count = cfg["blocks_num"] * cfg["block_size"] * cfg["head_num"] * cfg["head_dim"]
        src = torch.randn(element_count, dtype=torch.float32).clamp(-0.3, 0.3).to(torch.float16).to("xpu")

        quantized, scale_bytes = kvweave_quant_xpu.quantize_kvcache(
            src,
            cfg["qbit"],
            cfg["blocks_num"],
            cfg["block_size"],
            cfg["head_num"],
            cfg["head_dim"],
            cfg["rh"],
            cfg["asym"],
            cfg["scaling_method"],
            cfg["signs"],
            cfg["perm"],
        )

        kvweave_quant_xpu.reset_profile_stats()
        kvweave_quant_xpu.set_quant_profiling(True)
        try:
            for _ in range(50):
                kvweave_quant_xpu.dequantize_kvcache(
                    quantized,
                    scale_bytes,
                    cfg["qbit"],
                    cfg["blocks_num"],
                    cfg["block_size"],
                    cfg["head_num"],
                    cfg["head_dim"],
                    cfg["rh"],
                    cfg["asym"],
                    cfg["scaling_method"],
                    torch.float16,
                    cfg["signs"],
                    cfg["perm"],
                )
        finally:
            kvweave_quant_xpu.set_quant_profiling(False)

        stats = kvweave_quant_xpu.get_profile_stats()
        _print_stage_breakdown(
            f"dequantize_stage_breakdown_{scaling_method}_rh{rh}_pc{precond}",
            stats, _DEQUANTIZE_STAGES)
