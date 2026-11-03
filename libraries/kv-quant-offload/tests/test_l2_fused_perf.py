# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""L2 (native layer) performance benchmarks for the production KVWeave chains.

Covers the production fused-K/V attention and Mamba chains. Each test replays the
native call the LMCache codec issues (``serde_helpers.record_native_calls``), so the
L2 number is the native layer of the matching L3 test in test_l3_serde_perf.py.
CPU tests sweep ``num_threads``; XPU tests have no thread axis.
"""
from __future__ import annotations

import pytest
import torch

from kvweave import kvweave_quant
from conftest import (
    bench,
    print_bench_result,
    requires_xpu,
)

try:
    from kvweave import kvweave_quant_xpu
except ImportError:
    kvweave_quant_xpu = None


_PROD_PERF_THREADS = [1, 2, 4, 8, 16]


_PROD_ATTN_SCALING = ["per_channel", "per_token"]


def _fused_chain_native_calls(method):
    """Run the production fused-attention store+retrieve once through the codec
    and return ``(codec, raw, slot, payload_len, calls)`` where ``calls`` holds the
    exact args/kwargs of the native ``kvweave_*_chunk_state_into`` calls."""
    S = pytest.importorskip("serde_helpers")
    if kvweave_quant_xpu is None or not torch.xpu.is_available():
        pytest.skip("XPU is not available")
    from lmcache.v1.distributed.serde.kvweave.kvweave_config import AttentionPlaneLayout

    codec = S._fused_codec(method)
    raw = S._fused_attention_raw(seed=3)
    slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
    out = torch.empty_like(raw).pin_memory()
    layout = AttentionPlaneLayout.FUSED_KV
    names = ["kvweave_serialize_chunk_state_into", "kvweave_dequantize_chunk_state_into"]
    with S.record_native_calls(codec, names) as calls:
        written = codec.encode_chunk_into("attention", None, 64, None, raw, slot, layout)
        codec.decode_chunk("attention", None, 64, raw.shape, raw.dtype, slot[:written].clone(), layout, out)
    assert set(names) <= set(calls), f"production path did not use {names}: {list(calls)}"
    return codec, raw, slot, written, calls


@requires_xpu
@pytest.mark.perf
class TestL2ProductionFusedChainXpu:
    """Native layer of the production fused-attention chain (see test_l3_serde_perf.py for the chains).

    Replays the native call for a [8, 1024, 2048] fused chunk (per-head scales,
    num_layers = 8*head_num). Non-``_into`` variants are references.
    """

    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_serialize_chunk_state_into_fused_xpu(self, method, perf_collector):
        _, raw, slot, _, calls = _fused_chain_native_calls(method)
        args, kwargs = calls["kvweave_serialize_chunk_state_into"]
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            kvweave_quant_xpu.kvweave_serialize_chunk_state_into(*args, **kwargs)

        result = bench(_fn, warmup=5, iters=1000, data_bytes=data_bytes,
                       stage=f"l2_state_serialize_into_fused_{method}_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_serialize_chunk_state_bytes_fused_xpu(self, method, perf_collector):
        _, raw, _, _, calls = _fused_chain_native_calls(method)
        args, kwargs = calls["kvweave_serialize_chunk_state_into"]
        src, _dst, header, scale_id = args  # drop dst: bytes-returning variant
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            kvweave_quant_xpu.kvweave_serialize_chunk_state(src, header, scale_id, **kwargs)

        result = bench(_fn, warmup=5, iters=1000, data_bytes=data_bytes,
                       stage=f"l2_state_serialize_bytes_fused_{method}_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_dequantize_chunk_state_into_fused_xpu(self, method, perf_collector):
        _, raw, _, _, calls = _fused_chain_native_calls(method)
        args, kwargs = calls["kvweave_dequantize_chunk_state_into"]
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            kvweave_quant_xpu.kvweave_dequantize_chunk_state_into(*args, **kwargs)

        result = bench(_fn, warmup=5, iters=1000, data_bytes=data_bytes,
                       stage=f"l2_state_dequantize_into_fused_{method}_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_dequantize_chunk_state_fused_xpu(self, method, perf_collector):
        _, raw, _, _, calls = _fused_chain_native_calls(method)
        args, kwargs = calls["kvweave_dequantize_chunk_state_into"]
        q, scales, _dst, num_layers, tokens, native_hidden = args
        kwargs = {k: v for k, v in kwargs.items() if k != "merge_head_num"}
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            kvweave_quant_xpu.kvweave_dequantize_chunk_state(
                q, scales, num_layers, tokens, native_hidden, **kwargs)

        result = bench(_fn, warmup=5, iters=1000, data_bytes=data_bytes,
                       stage=f"l2_state_dequantize_new_tensor_fused_{method}_xpu")
        print_bench_result(result)
        perf_collector.append(result)


@requires_xpu
@pytest.mark.perf
class TestL2ProductionMambaChainXpu:
    """Native layer of the production Mamba (linear attention) chain.

    Chain: encode_chunk (mamba branch) -> _quantize_mamba_jobs ->
    kvweave_serialize_chunk_state_multi (conv q/k/v, fp16 batch) +
    kvweave_serialize_chunk_state (ssm, fp32 singleton); retrieve mirrors it with
    kvweave_dequantize_chunk_state_multi / kvweave_dequantize_chunk_state.
    Geometry: Qwen3.5-9B, 8 layers x 1 block of 1024 tokens, conv (3, 8192)
    fp16 + ssm (32, 128, 128) fp32, per_token + rh, qbit 4.
    """

    @staticmethod
    def _calls():
        S = pytest.importorskip("serde_helpers")
        if kvweave_quant_xpu is None or not torch.xpu.is_available():
            pytest.skip("XPU is not available")
        codec, layouts, options, raw, block_size = S._mamba_prod_case(seed=5)
        slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
        out = torch.empty_like(raw).pin_memory()
        names = [
            "kvweave_serialize_chunk_state_multi", "kvweave_serialize_chunk_state",
            "kvweave_dequantize_chunk_state_multi", "kvweave_dequantize_chunk_state",
        ]
        with S.record_native_calls(codec, names) as calls:
            written = codec.encode_chunk_into("mamba", layouts, block_size, options, raw, slot)
            codec.decode_chunk("mamba", layouts, block_size, raw.shape, raw.dtype,
                               slot[:written].clone(), None, out)
        return raw, calls

    def test_serialize_chunk_state_mamba_xpu(self, perf_collector):
        raw, calls = self._calls()
        multi = calls["kvweave_serialize_chunk_state_multi"]
        single = calls["kvweave_serialize_chunk_state"]
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            kvweave_quant_xpu.kvweave_serialize_chunk_state_multi(*multi[0], **multi[1])
            kvweave_quant_xpu.kvweave_serialize_chunk_state(*single[0], **single[1])

        result = bench(_fn, warmup=5, iters=200, data_bytes=data_bytes,
                       stage="l2_state_serialize_mamba_multi_plus_ssm_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    def test_dequantize_chunk_state_mamba_xpu(self, perf_collector):
        raw, calls = self._calls()
        multi = calls["kvweave_dequantize_chunk_state_multi"]
        single = calls["kvweave_dequantize_chunk_state"]
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            kvweave_quant_xpu.kvweave_dequantize_chunk_state_multi(*multi[0], **multi[1])
            kvweave_quant_xpu.kvweave_dequantize_chunk_state(*single[0], **single[1])

        result = bench(_fn, warmup=5, iters=200, data_bytes=data_bytes,
                       stage="l2_state_dequantize_mamba_multi_plus_ssm_xpu")
        print_bench_result(result)
        perf_collector.append(result)


# ---------------------------------------------------------------------------
# CPU (default production device): fused attention + Mamba, thread sweep
# ---------------------------------------------------------------------------
_THREAD_IDS = ["t1", "t2", "t4", "t8", "t16"]


_CPU_DIRECT_NAMES = ["kvweave_serialize_fused_chunk_direct", "kvweave_dequantize_fused_chunk_direct"]


def _fused_chain_native_calls_cpu(method):
    """Run the CPU fused-attention store+retrieve once through the codec and return
    ``(raw, calls)`` with the exact native ``kvweave_*_fused_chunk_direct`` call args."""
    S = pytest.importorskip("serde_helpers")
    from lmcache.v1.distributed.serde.kvweave.kvweave_config import AttentionPlaneLayout

    codec = S._fused_codec(method, device="cpu")
    raw = S._fused_attention_raw(seed=3, pinned=False)
    slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
    out = torch.empty_like(raw)
    layout = AttentionPlaneLayout.FUSED_KV
    with S.record_native_calls(codec, _CPU_DIRECT_NAMES) as calls:
        written = codec.encode_chunk_into("attention", None, 64, None, raw, slot, layout)
        codec.decode_chunk("attention", None, 64, raw.shape, raw.dtype, slot[:written].clone(), layout, out)
    assert set(_CPU_DIRECT_NAMES) <= set(calls), f"CPU path did not use {_CPU_DIRECT_NAMES}: {list(calls)}"
    return raw, calls


@pytest.mark.perf
class TestL2ProductionFusedDirectCpu:
    """CPU native layer of the production fused-attention chain ([8, 1024, 2048]).

    store    : kvweave_serialize_fused_chunk_direct   (reads the fused layout directly)
    retrieve : kvweave_dequantize_fused_chunk_direct  (writes the fused layout directly)
    """

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=_THREAD_IDS)
    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_serialize_fused_direct_cpu(self, method, num_threads, perf_collector):
        raw, calls = _fused_chain_native_calls_cpu(method)
        args, kwargs = calls["kvweave_serialize_fused_chunk_direct"]
        kwargs = dict(kwargs, num_threads=num_threads)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            kvweave_quant.kvweave_serialize_fused_chunk_direct(*args, **kwargs)

        result = bench(_fn, warmup=5, iters=200, data_bytes=data_bytes,
                       stage=f"l2_serialize_fused_direct_{method}_cpu_t{num_threads}")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=_THREAD_IDS)
    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_dequantize_fused_direct_cpu(self, method, num_threads, perf_collector):
        raw, calls = _fused_chain_native_calls_cpu(method)
        args, kwargs = calls["kvweave_dequantize_fused_chunk_direct"]
        kwargs = dict(kwargs, num_threads=num_threads)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            kvweave_quant.kvweave_dequantize_fused_chunk_direct(*args, **kwargs)

        result = bench(_fn, warmup=5, iters=200, data_bytes=data_bytes,
                       stage=f"l2_dequantize_fused_direct_{method}_cpu_t{num_threads}")
        print_bench_result(result)
        perf_collector.append(result)


@pytest.mark.perf
class TestL2ProductionMambaChainCpu:
    """CPU native layer of the Mamba chain: the CPU module has no ``_multi`` entry, so
    each of the 4 substates (conv q/k/v, ssm) is one ``kvweave_*_chunk_state`` call. The
    recorded calls are replayed with ``num_threads`` overridden (thread sweep)."""

    @staticmethod
    def _calls():
        S = pytest.importorskip("serde_helpers")
        codec, layouts, options, raw, block_size = S._mamba_prod_case(seed=5, device="cpu", pinned=False)
        slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
        out = torch.empty_like(raw)
        names = ["kvweave_serialize_chunk_state", "kvweave_dequantize_chunk_state"]
        with S.record_native_calls(codec, names) as calls:
            written = codec.encode_chunk_into("mamba", layouts, block_size, options, raw, slot)
            codec.decode_chunk("mamba", layouts, block_size, raw.shape, raw.dtype,
                               slot[:written].clone(), None, out)
        assert all(len(calls[n + "#all"]) == 4 for n in names), "expected 4 substate calls"
        return raw, calls

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=_THREAD_IDS)
    def test_serialize_chunk_state_mamba_cpu(self, num_threads, perf_collector):
        raw, calls = self._calls()
        batch = calls["kvweave_serialize_chunk_state#all"]
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            for args, kwargs in batch:
                kvweave_quant.kvweave_serialize_chunk_state(*args, **dict(kwargs, num_threads=num_threads))

        result = bench(_fn, warmup=3, iters=100, data_bytes=data_bytes,
                       stage=f"l2_state_serialize_mamba_4substates_cpu_t{num_threads}")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=_THREAD_IDS)
    def test_dequantize_chunk_state_mamba_cpu(self, num_threads, perf_collector):
        raw, calls = self._calls()
        batch = calls["kvweave_dequantize_chunk_state#all"]
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            for args, kwargs in batch:
                kvweave_quant.kvweave_dequantize_chunk_state(*args, **dict(kwargs, num_threads=num_threads))

        result = bench(_fn, warmup=3, iters=100, data_bytes=data_bytes,
                       stage=f"l2_state_dequantize_mamba_4substates_cpu_t{num_threads}")
        print_bench_result(result)
        perf_collector.append(result)
