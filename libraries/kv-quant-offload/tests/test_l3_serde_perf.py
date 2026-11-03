# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""L3 (codec layer) performance benchmarks for the production KVWeave LMCache codec.

Production fused-K/V attention and Mamba chains through ``_KVWeaveCodec`` on CPU
(default, swept over ``num_threads``) and XPU. Shared helpers come from
serde_helpers.py (importing it also skips this file when kvweave_serde is unavailable).
"""
from __future__ import annotations

import pytest
import torch

from conftest import (
    PROD_CHUNK_TOKENS,
    bench,
    print_bench_result,
)
from serde_helpers import _PROD_PERF_THREADS

_PROD_ATTN_SCALING = ["per_channel", "per_token"]


@pytest.mark.perf
class TestL3ProductionChainXpu:
    """Production chains through the patched LMCache codec on XPU.

    Fused attention (FUSED_KV, [8, 1024, 2048] fp16 pinned, per-head scales):
      store    encode_chunk_into -> serialize_fused_tensor(out=slot)
               -> kvweave_serialize_chunk_state_into
      retrieve decode_chunk -> deserialize_fused_tensor
               -> kvweave_dequantize_chunk_state_into
    Mamba (linear attention conv/ssm, 8 layers x 1024 tokens):
      store    encode_chunk (mamba branch) -> kvweave_serialize_chunk_state_multi
               (+ ssm singleton), payload then copied into the slot
      retrieve decode_chunk -> kvweave_dequantize_chunk_state_multi (+ ssm)
               -> merge_mamba_chunk
    Production store splits into persistent pool scratch before encode_chunk_into,
    so encode tests pass a pre-split; the "inline_split" test is a reference for
    splitting inside the call. num_threads=8 as in production. L2 counterparts:
    test_l2_fused_perf.py.
    """

    @staticmethod
    def _require_xpu():
        pytest.importorskip("kvweave.kvweave_quant_xpu")
        if not torch.xpu.is_available():
            pytest.skip("XPU is not available")

    @staticmethod
    def _fused_case(method):
        from lmcache.v1.distributed.serde.kvweave.kvweave_config import AttentionPlaneLayout
        from serde_helpers import PROD_ATTN_LAYERS, _fused_attention_raw, _fused_codec

        codec = _fused_codec(method)
        raw = _fused_attention_raw(seed=3)
        slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
        layout = AttentionPlaneLayout.FUSED_KV
        written = codec.encode_chunk_into("attention", None, 64, None, raw, slot, layout)
        # persistent per-head split, like the pool scratch production passes in
        head_split = torch.empty(
            PROD_ATTN_LAYERS * codec._fused_head_num(raw.shape[-1]), raw.shape[1],
            codec._fused_head_dim(raw.shape[-1]), dtype=raw.dtype,
        )
        codec.split_fused_attention_heads(
            raw, codec._fused_head_num(raw.shape[-1]), codec._fused_head_dim(raw.shape[-1]),
            out=head_split, num_threads=codec.num_threads,
        )
        return codec, raw, slot, written, layout, head_split

    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_encode_chunk_into_fused_xpu(self, method, perf_collector):
        self._require_xpu()
        codec, raw, slot, _, layout, head_split = self._fused_case(method)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.encode_chunk_into("attention", None, 64, None, raw, slot, layout,
                                    None, head_split)

        result = bench(_fn, warmup=5, iters=100, data_bytes=data_bytes,
                       stage=f"l3_encode_chunk_into_fused_{method}_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    def test_encode_chunk_into_fused_inline_split_xpu(self, perf_collector):
        """Reference only: split done inside the call (fresh 33.5 MB temporary each time)."""
        self._require_xpu()
        codec, raw, slot, _, layout, _ = self._fused_case("per_channel")
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.encode_chunk_into("attention", None, 64, None, raw, slot, layout)

        result = bench(_fn, warmup=5, iters=100, data_bytes=data_bytes,
                       stage="l3_encode_chunk_into_fused_inline_split_per_channel_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    def test_split_fused_attention_heads_scratch(self, perf_collector):
        """Production store stage 1 (CPU): [L,T,H*D] -> per-head rows into persistent scratch."""
        self._require_xpu()
        codec, raw, _, _, _, head_split = self._fused_case("per_channel")
        head_num = codec._fused_head_num(raw.shape[-1])
        head_dim = codec._fused_head_dim(raw.shape[-1])
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.split_fused_attention_heads(
                raw, head_num, head_dim, out=head_split, num_threads=codec.num_threads)

        result = bench(_fn, warmup=5, iters=100, data_bytes=data_bytes,
                       stage="l3_split_fused_attention_heads_scratch")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_serialize_fused_tensor_into_xpu(self, method, perf_collector):
        self._require_xpu()
        codec, raw, slot, _, _, head_split = self._fused_case(method)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.serialize_fused_tensor(raw, head_split=head_split, out=slot)

        result = bench(_fn, warmup=5, iters=100, data_bytes=data_bytes,
                       stage=f"l3_serialize_fused_tensor_into_{method}_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_decode_chunk_fused_xpu(self, method, perf_collector):
        self._require_xpu()
        codec, raw, slot, written, layout, _ = self._fused_case(method)
        chunk = slot[:written].clone()
        out = torch.empty_like(raw).pin_memory()
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.decode_chunk("attention", None, 64, raw.shape, raw.dtype, chunk, layout, out)

        result = bench(_fn, warmup=5, iters=100, data_bytes=data_bytes,
                       stage=f"l3_decode_chunk_fused_{method}_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_deserialize_fused_tensor_xpu(self, method, perf_collector):
        self._require_xpu()
        codec, raw, slot, written, _, _ = self._fused_case(method)
        chunk = slot[:written].clone()
        out = torch.empty_like(raw).pin_memory()
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.deserialize_fused_tensor(chunk, out)

        result = bench(_fn, warmup=5, iters=100, data_bytes=data_bytes,
                       stage=f"l3_deserialize_fused_tensor_{method}_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    def test_encode_chunk_into_mamba_xpu(self, perf_collector):
        self._require_xpu()
        from serde_helpers import _mamba_prod_case

        codec, layouts, options, raw, block_size = _mamba_prod_case(seed=5)
        slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
        data_bytes = raw.numel() * raw.element_size()
        split = self._mamba_scratch_split(codec, layouts, raw, block_size)

        def _fn():
            codec.encode_chunk_into("mamba", layouts, block_size, options, raw, slot,
                                    None, split)

        result = bench(_fn, warmup=3, iters=100, data_bytes=data_bytes,
                       stage="l3_encode_chunk_into_mamba_xpu")
        print_bench_result(result)
        perf_collector.append(result)

    @staticmethod
    def _mamba_scratch_split(codec, layouts, raw, block_size):
        """Persistent conv/ssm split buffers, like the pool scratch production uses."""
        from lmcache.v1.distributed.serde.kvweave.kvweave_serde import MambaChunkSplit

        template = codec.split_mamba_chunk(raw, layouts, block_size)
        split = MambaChunkSplit(torch.empty_like(template.conv), torch.empty_like(template.ssm))
        codec.split_mamba_chunk(raw, layouts, block_size, out=split)
        return split

    def test_split_mamba_chunk_scratch(self, perf_collector):
        """Production Mamba store stage 1 (CPU): page view -> real conv/ssm bytes into scratch."""
        self._require_xpu()
        from serde_helpers import _mamba_prod_case

        codec, layouts, _, raw, block_size = _mamba_prod_case(seed=5)
        split = self._mamba_scratch_split(codec, layouts, raw, block_size)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.split_mamba_chunk(raw, layouts, block_size, out=split)

        result = bench(_fn, warmup=3, iters=100, data_bytes=data_bytes,
                       stage="l3_split_mamba_chunk_scratch")
        print_bench_result(result)
        perf_collector.append(result)

    def test_decode_chunk_mamba_xpu(self, perf_collector):
        self._require_xpu()
        from serde_helpers import _mamba_prod_case

        codec, layouts, options, raw, block_size = _mamba_prod_case(seed=5)
        slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
        written = codec.encode_chunk_into("mamba", layouts, block_size, options, raw, slot)
        chunk = slot[:written].clone()
        out = torch.empty_like(raw).pin_memory()
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.decode_chunk("mamba", layouts, block_size, raw.shape, raw.dtype, chunk, None, out)

        result = bench(_fn, warmup=3, iters=100, data_bytes=data_bytes,
                       stage="l3_decode_chunk_mamba_xpu")
        print_bench_result(result)
        perf_collector.append(result)


_THREAD_IDS = ["t1", "t2", "t4", "t8", "t16"]
# torch intra-op threads for host copies: None = torch default (production), 1 = single-threaded.
_TORCH_THREADS = [None, 1]
_TORCH_THREAD_IDS = ["tt_default", "tt1"]


@pytest.fixture
def torch_threads(request):
    n = request.param
    previous = torch.get_num_threads()
    if n is not None:
        torch.set_num_threads(n)
    yield n
    torch.set_num_threads(previous)


@pytest.mark.perf
class TestL3ProductionChainCpu:
    """CPU fused-attention and Mamba chains via the codec, as in TestL3ProductionChainXpu with ``codec.num_threads`` swept.

    Fused attention uses the direct fused-chunk calls (no head split/merge); Mamba is also swept over torch intra-op threads.
    """

    @staticmethod
    def _fused_case(method, num_threads):
        from lmcache.v1.distributed.serde.kvweave.kvweave_config import AttentionPlaneLayout
        from serde_helpers import _fused_attention_raw, _fused_codec

        codec = _fused_codec(method, num_threads=num_threads, device="cpu")
        raw = _fused_attention_raw(seed=3, pinned=False)
        slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
        layout = AttentionPlaneLayout.FUSED_KV
        written = codec.encode_chunk_into("attention", None, 64, None, raw, slot, layout)
        return codec, raw, slot, written, layout

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=_THREAD_IDS)
    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_encode_chunk_into_fused_cpu(self, method, num_threads, perf_collector):
        codec, raw, slot, _, layout = self._fused_case(method, num_threads)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.encode_chunk_into("attention", None, 64, None, raw, slot, layout)

        result = bench(_fn, warmup=3, iters=50, data_bytes=data_bytes,
                       stage=f"l3_encode_chunk_into_fused_{method}_cpu_t{num_threads}")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=_THREAD_IDS)
    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_decode_chunk_fused_cpu(self, method, num_threads, perf_collector):
        codec, raw, slot, written, layout = self._fused_case(method, num_threads)
        chunk = slot[:written].clone()
        out = torch.empty_like(raw)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.decode_chunk("attention", None, 64, raw.shape, raw.dtype, chunk, layout, out)

        result = bench(_fn, warmup=3, iters=50, data_bytes=data_bytes,
                       stage=f"l3_decode_chunk_fused_{method}_cpu_t{num_threads}")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("torch_threads", _TORCH_THREADS, ids=_TORCH_THREAD_IDS, indirect=True)
    @pytest.mark.parametrize("method", _PROD_ATTN_SCALING)
    def test_encode_chunk_into_fused_cpu_torch_threads(self, method, torch_threads, perf_collector):
        """num_threads=8 (production), varying torch's intra-op threads (payload -> slot copy)."""
        codec, raw, slot, _, layout = self._fused_case(method, 8)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.encode_chunk_into("attention", None, 64, None, raw, slot, layout)

        result = bench(_fn, warmup=3, iters=50, data_bytes=data_bytes,
                       stage=f"l3_encode_chunk_into_fused_{method}_cpu_t8_torch{torch_threads or 'default'}")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("torch_threads", _TORCH_THREADS, ids=_TORCH_THREAD_IDS, indirect=True)
    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=_THREAD_IDS)
    def test_encode_chunk_into_mamba_cpu(self, num_threads, torch_threads, perf_collector):
        from serde_helpers import _mamba_prod_case

        codec, layouts, options, raw, block_size = _mamba_prod_case(
            seed=5, device="cpu", pinned=False, num_threads=num_threads
        )
        slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
        template = codec.split_mamba_chunk(raw, layouts, block_size)
        from lmcache.v1.distributed.serde.kvweave.kvweave_serde import MambaChunkSplit

        split = MambaChunkSplit(torch.empty_like(template.conv), torch.empty_like(template.ssm))
        codec.split_mamba_chunk(raw, layouts, block_size, out=split)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.encode_chunk_into("mamba", layouts, block_size, options, raw, slot, None, split)

        result = bench(_fn, warmup=3, iters=50, data_bytes=data_bytes,
                       stage=f"l3_encode_chunk_into_mamba_cpu_t{num_threads}_torch{torch_threads or 'default'}")
        print_bench_result(result)
        perf_collector.append(result)

    @pytest.mark.parametrize("torch_threads", _TORCH_THREADS, ids=_TORCH_THREAD_IDS, indirect=True)
    @pytest.mark.parametrize("num_threads", _PROD_PERF_THREADS, ids=_THREAD_IDS)
    def test_decode_chunk_mamba_cpu(self, num_threads, torch_threads, perf_collector):
        from serde_helpers import _mamba_prod_case

        codec, layouts, options, raw, block_size = _mamba_prod_case(
            seed=5, device="cpu", pinned=False, num_threads=num_threads
        )
        slot = torch.zeros(raw.numel() * raw.element_size(), dtype=torch.uint8)
        written = codec.encode_chunk_into("mamba", layouts, block_size, options, raw, slot)
        chunk = slot[:written].clone()
        out = torch.empty_like(raw)
        data_bytes = raw.numel() * raw.element_size()

        def _fn():
            codec.decode_chunk("mamba", layouts, block_size, raw.shape, raw.dtype, chunk, None, out)

        result = bench(_fn, warmup=3, iters=50, data_bytes=data_bytes,
                       stage=f"l3_decode_chunk_mamba_cpu_t{num_threads}_torch{torch_threads or 'default'}")
        print_bench_result(result)
        perf_collector.append(result)
