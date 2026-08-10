# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""L3 performance benchmarks for the production KVWeave LMCache serde codec.

Production-shaped microbenchmarks for _KVWeaveCodec.serialize_tensor /
deserialize_tensor on 4D [2, num_layers, T, H*D] tensors. Shared codec helpers
come from serde_helpers.py (importing it also skip-guards this file when
kvweave_serde, sourced from the patched LMCache tree, is unavailable).
"""
from __future__ import annotations

import pytest
import torch

from conftest import (
    PROD_CHUNK_TOKENS,
    PROD_NUM_LAYERS,
    bench,
    print_bench_result,
)
from serde_helpers import (
    kvweave_quant,
    _PROD_PERF_THREADS,
    _PROD_THREAD_SCENARIOS,
    _PROD_THREAD_STRATEGIES,
    _attention_chunk_4d,
    _codec,
    _cpu_dequantize_into_4d_with_thread_strategy,
    _payload_tensor,
    _prepare_deserialize_case_4d,
)


@pytest.mark.perf
class TestL3SerdePerf:
    """Production-shaped codec microbenchmarks for 4D [2,1,T,H] tensors."""

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_serialize_tensor_prod_chunk_4d(self, num_threads, perf_collector):
        codec = _codec(num_threads=num_threads)
        source = _attention_chunk_4d(chunk_tokens=PROD_CHUNK_TOKENS, seed=20)
        data_bytes = source.numel() * source.element_size()

        def _fn():
            codec.serialize_tensor(source)

        result = bench(
            _fn,
            warmup=5,
            iters=50,
            data_bytes=data_bytes,
            stage=f"l3_serde_serialize_4d_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)


@pytest.mark.perf
class TestL3SerdeThreadStrategy:
    """Thread-placement comparison for full-depth (PROD_NUM_LAYERS) 4D deserialize.

    Covers a representative subset (block- vs layer-parallel placement x
    preconditioned vs non-preconditioned scaling) rather than the full
    strategy x scenario grid.
    """

    @pytest.mark.parametrize(
        ("strategy", "block_num_threads", "layer_num_threads"),
        _PROD_THREAD_STRATEGIES,
        ids=[cfg[0] for cfg in _PROD_THREAD_STRATEGIES],
    )
    def test_deserialize_tensor_prod_chunk_4d_thread_strategy(
        self,
        strategy,
        block_num_threads,
        layer_num_threads,
        perf_collector,
    ):
        if not hasattr(kvweave_quant, "kvweave_dequantize_chunk_into_4d"):
            pytest.skip("direct 4D dequant path is not available")

        case = _prepare_deserialize_case_4d(
            max(1, block_num_threads),
            seed=30,
            num_layers=PROD_NUM_LAYERS,
            chunk_tokens=PROD_CHUNK_TOKENS,
        )
        parsed = case["parsed"]
        dst = case["dst"]
        data_bytes = case["source"].numel() * case["source"].element_size()

        def _fn():
            _cpu_dequantize_into_4d_with_thread_strategy(
                parsed,
                dst,
                block_num_threads=block_num_threads,
                layer_num_threads=layer_num_threads,
            )

        result = bench(
            _fn,
            warmup=2,
            iters=10,
            data_bytes=data_bytes,
            stage=f"l3_serde_deserialize_4d_{strategy}",
        )
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize(
        ("scenario", "scaling_method", "rh"),
        _PROD_THREAD_SCENARIOS,
        ids=[cfg[0] for cfg in _PROD_THREAD_SCENARIOS],
    )
    @pytest.mark.parametrize(
        ("strategy", "block_num_threads", "layer_num_threads"),
        _PROD_THREAD_STRATEGIES,
        ids=[cfg[0] for cfg in _PROD_THREAD_STRATEGIES],
    )
    def test_deserialize_tensor_prod_chunk_4d_thread_strategy_variants(
        self,
        scenario,
        scaling_method,
        rh,
        strategy,
        block_num_threads,
        layer_num_threads,
        perf_collector,
    ):
        if not hasattr(kvweave_quant, "kvweave_dequantize_chunk_into_4d"):
            pytest.skip("direct 4D dequant path is not available")

        case = _prepare_deserialize_case_4d(
            max(1, block_num_threads),
            seed=31,
            num_layers=PROD_NUM_LAYERS,
            chunk_tokens=PROD_CHUNK_TOKENS,
            scaling_method=scaling_method,
            rh=rh,
            include_restored_4d=False,
        )
        parsed = case["parsed"]
        dst = case["dst"]
        data_bytes = case["source"].numel() * case["source"].element_size()

        def _fn():
            _cpu_dequantize_into_4d_with_thread_strategy(
                parsed,
                dst,
                block_num_threads=block_num_threads,
                layer_num_threads=layer_num_threads,
            )

        result = bench(
            _fn,
            warmup=2,
            iters=10,
            data_bytes=data_bytes,
            stage=f"l3_serde_deserialize_4d_{scenario}_{strategy}",
        )
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_deserialize_tensor_prod_chunk_4d(self, num_threads, perf_collector):
        codec = _codec(num_threads=num_threads)
        source = _attention_chunk_4d(chunk_tokens=PROD_CHUNK_TOKENS, seed=21)
        payload = codec.serialize_tensor(source)
        payload_tensor = _payload_tensor(payload)
        dst = torch.empty_like(source)
        data_bytes = source.numel() * source.element_size()

        def _fn():
            codec.deserialize_tensor(payload_tensor, dst)

        result = bench(
            _fn,
            warmup=5,
            iters=50,
            data_bytes=data_bytes,
            stage=f"l3_serde_deserialize_4d_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_deserialize_tensor_prod_chunk_4d_direct(self, num_threads, perf_collector):
        if not hasattr(kvweave_quant, "kvweave_dequantize_chunk_into_4d"):
            pytest.skip("direct 4D dequant path is not available")

        codec = _codec(num_threads=num_threads)
        source = _attention_chunk_4d(chunk_tokens=PROD_CHUNK_TOKENS, seed=23)
        payload = codec.serialize_tensor(source)
        parsed = codec._parse_payload(payload)
        dst = torch.empty_like(source)
        data_bytes = source.numel() * source.element_size()

        def _fn():
            codec._cpu_dequantize_into_4d(parsed, dst)

        result = bench(
            _fn,
            warmup=5,
            iters=50,
            data_bytes=data_bytes,
            stage=f"l3_serde_deserialize_4d_direct_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_deserialize_tensor_prod_chunk_4d_multilayer(self, num_threads, perf_collector):
        codec = _codec(num_threads=num_threads)
        source = _attention_chunk_4d(
            chunk_tokens=PROD_CHUNK_TOKENS,
            num_layers=3,
            seed=24,
        )
        payload = codec.serialize_tensor(source)
        payload_tensor = _payload_tensor(payload)
        dst = torch.empty_like(source)
        data_bytes = source.numel() * source.element_size()

        def _fn():
            codec.deserialize_tensor(payload_tensor, dst)

        result = bench(
            _fn,
            warmup=5,
            iters=50,
            data_bytes=data_bytes,
            stage=f"l3_serde_deserialize_4d_ml3_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=["t1", "t2", "t4", "t8", "t16"])
    def test_deserialize_tensor_prod_chunk_4d_multilayer_direct(self, num_threads, perf_collector):
        if not hasattr(kvweave_quant, "kvweave_dequantize_chunk_into_4d"):
            pytest.skip("direct 4D dequant path is not available")

        codec = _codec(num_threads=num_threads)
        source = _attention_chunk_4d(
            chunk_tokens=PROD_CHUNK_TOKENS,
            num_layers=3,
            seed=25,
        )
        payload = codec.serialize_tensor(source)
        parsed = codec._parse_payload(payload)
        dst = torch.empty_like(source)
        data_bytes = source.numel() * source.element_size()

        def _fn():
            codec._cpu_dequantize_into_4d(parsed, dst)

        result = bench(
            _fn,
            warmup=5,
            iters=50,
            data_bytes=data_bytes,
            stage=f"l3_serde_deserialize_4d_direct_ml3_t{num_threads}",
        )
        print_bench_result(result)
        perf_collector.append(result)
