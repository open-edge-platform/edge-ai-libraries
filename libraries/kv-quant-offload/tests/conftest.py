# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures, utilities, and configuration for kvweave unit tests."""
from __future__ import annotations

import json
import struct
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import pytest
import torch

from kvweave import kvweave_quant

try:
    from kvweave import kvweave_quant_xpu
except ImportError:
    kvweave_quant_xpu = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Production config (Qwen3.5-9B, integration/vllm/vllm-start.sh). Qwen3.5-9B
# is a hybrid linear/full-attention model (32 decoder layers total, 3:1
# linear:full-attention ratio); both layer types are quantized through this
# codec, so PROD_NUM_LAYERS reflects the full decoder depth for multi-layer
# replay scenarios. Single-layer correctness tests pass their own explicit
# num_layers=1 and don't reference this constant.
PROD_NUM_LAYERS = 32
PROD_NUM_KV_HEADS = 4
PROD_HEAD_DIM = 256
PROD_H_MERGED = PROD_NUM_KV_HEADS * PROD_HEAD_DIM  # 1024
PROD_CHUNK_TOKENS = 1024
PROD_BLOCK_SIZE = 1024
PROD_NUM_THREADS = 1
PROD_DTYPE = torch.float16


# ---------------------------------------------------------------------------
# Parametrized fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(params=[torch.float16, torch.bfloat16], ids=["fp16", "bf16"])
def dtype(request):
    return request.param


@pytest.fixture(params=[4], ids=["4bit"])
def qbit(request):
    return request.param


@pytest.fixture(params=["per_tensor", "per_token", "per_channel"],
                ids=["per_tensor", "per_token", "per_channel"])
def scaling_method(request):
    return request.param


@pytest.fixture(params=[(False, False), (True, False), (True, True)],
                ids=["no_rh", "rh_no_precond", "rh_precond"])
def rh_precond(request):
    return request.param


@pytest.fixture(params=[False, True], ids=["sym", "asym"])
def asym(request):
    return request.param


# ---------------------------------------------------------------------------
# Tensor generation
# ---------------------------------------------------------------------------

def generate_chunk(
    chunk_tokens: int = PROD_CHUNK_TOKENS,
    head_num: int = PROD_NUM_KV_HEADS,
    head_dim: int = PROD_HEAD_DIM,
    dtype: torch.dtype = torch.float16,
    seed: int = 0,
) -> torch.Tensor:
    """Generate a [T, 2, H*D] float tensor simulating one KV-cache chunk.

    Values are normally distributed with 1% outliers (matches real KV-cache).
    """
    total = chunk_tokens * 2 * head_num * head_dim
    g = torch.Generator().manual_seed(seed)
    t = torch.randn(total, generator=g, dtype=torch.float32) * 0.05
    t = t.clamp(-0.3, 0.3)
    mask = torch.rand(total, generator=g) < 0.01
    outliers = torch.rand(int(mask.sum().item()), generator=g) * 10.0 - 5.0
    t[mask] = outliers
    return t.to(dtype).reshape(chunk_tokens, 2, head_num * head_dim)


@pytest.fixture
def kv_chunk(dtype):
    """Standard [T, 2, H*D] KV-cache chunk."""
    return generate_chunk(dtype=dtype)


# ---------------------------------------------------------------------------
# Production-config (Qwen3-8B) helpers
# ---------------------------------------------------------------------------

def make_paged_kvcache(
    num_blocks: int,
    num_kv_heads: int = PROD_NUM_KV_HEADS,
    block_size: int = PROD_BLOCK_SIZE,
    head_dim: int = PROD_HEAD_DIM,
    dtype: torch.dtype = PROD_DTYPE,
    device: str = "xpu",
) -> torch.Tensor:
    """Allocate one layer's paged KV cache: [2, num_blocks, block_size, H, D].

    Matches the vLLM non-MLA flash-attention NHD layout (list-of-per-layer
    tensors, ``GPUKVFormat.NL_X_TWO_NB_BS_NH_HS``) that
    ``normalize_kv_and_discover_format`` discovers for a single-tensor list.
    """
    return torch.empty(
        2, num_blocks, block_size, num_kv_heads, head_dim, dtype=dtype, device=device
    )


# ---------------------------------------------------------------------------
# Preconditioning
# ---------------------------------------------------------------------------

def preconditioning_size_for_half(
    scaling_method: str,
    half_elements: int,
    blocks_num_half: int,
    block_size: int,
    head_dim: int,
) -> int:
    """Compute the Hadamard/precond dimension for one K or V half."""
    if scaling_method == "per_token":
        return half_elements // (blocks_num_half * block_size)
    if scaling_method == "per_channel":
        return half_elements // head_dim
    return half_elements


def generate_preconditioning(dim: int, seed: int = 42) -> Tuple[torch.Tensor, torch.Tensor]:
    """Generate random signs ({+1,-1}) and permutation for preconditioning."""
    rng = np.random.default_rng(seed)
    signs = torch.from_numpy(rng.choice([-1.0, 1.0], size=dim).astype(np.float32))
    perm = torch.from_numpy(rng.permutation(dim).astype(np.int32))
    return signs, perm


# ---------------------------------------------------------------------------
# Quantization config builder
# ---------------------------------------------------------------------------

def build_quant_cfg(
    qbit: int = 4,
    scaling_method: str = "per_channel",
    rh: bool = True,
    asym: bool = True,
    precond: bool = True,
    chunk_tokens: int = PROD_CHUNK_TOKENS,
    head_num: int = PROD_NUM_KV_HEADS,
    head_dim: int = PROD_HEAD_DIM,
    num_threads: int = PROD_NUM_THREADS,
    blocks_num: Optional[int] = None,
) -> dict:
    """Build a complete quantization config dict."""
    if blocks_num is None:
        blocks_num = chunk_tokens // PROD_BLOCK_SIZE
    half_elements = chunk_tokens * head_num * head_dim

    signs = None
    perm = None
    if precond and rh:
        h_size = preconditioning_size_for_half(
            scaling_method, half_elements, blocks_num, PROD_BLOCK_SIZE, head_dim
        )
        signs, perm = generate_preconditioning(h_size)

    return {
        "qbit": qbit,
        "scaling_method": scaling_method,
        "rh": rh,
        "asym": asym,
        "precond": precond,
        "blocks_num": blocks_num,
        "block_size": PROD_BLOCK_SIZE,
        "head_num": head_num,
        "head_dim": head_dim,
        "chunk_tokens": chunk_tokens,
        "num_threads": num_threads,
        "signs": signs,
        "perm": perm,
    }


@pytest.fixture
def quant_cfg(qbit, scaling_method, rh_precond, asym):
    """Parametrized quantization config fixture."""
    rh, precond = rh_precond
    return build_quant_cfg(
        qbit=qbit,
        scaling_method=scaling_method,
        rh=rh,
        asym=asym,
        precond=precond,
    )


# ---------------------------------------------------------------------------
# Quant/dequant roundtrip helper
# ---------------------------------------------------------------------------

_SCALE_ID_COUNTER = 0


def _next_scale_id() -> int:
    global _SCALE_ID_COUNTER
    _SCALE_ID_COUNTER += 1
    return 0x100000 + _SCALE_ID_COUNTER * 4


def quant_dequant_roundtrip(
    tensor: torch.Tensor,
    cfg: dict,
    scale_id: int = None,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Quantize then dequantize, returning (quantized, restored)."""
    if scale_id is None:
        scale_id = _next_scale_id()
    quantized = kvweave_quant.quantize_kvcache(
        tensor,
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

    dq_scale_id = scale_id + 0x10000
    kvweave_quant.set_scales_for_id(dq_scale_id, scales_bytes)
    restored = kvweave_quant.dequantize_kvcache(
        quantized,
        scale_id=dq_scale_id,
        qbit=cfg["qbit"],
        blocks_num=cfg["blocks_num"],
        block_size=cfg["block_size"],
        head_num=cfg["head_num"],
        head_dim=cfg["head_dim"],
        rh=cfg["rh"],
        asym=cfg["asym"],
        scaling_method=cfg["scaling_method"],
        output_dtype=tensor.dtype,
        signs=cfg["signs"],
        perm=cfg["perm"],
        num_threads=cfg["num_threads"],
    )
    kvweave_quant.clear_scales_for_id(scale_id)
    kvweave_quant.clear_scales_for_id(dq_scale_id)
    return quantized, restored


# ---------------------------------------------------------------------------
# XPU quant/dequant roundtrip helper
# ---------------------------------------------------------------------------
# kvweave_quant_xpu has no scale_id table (quantize/dequantize return/consume
# the scale blob directly) and no num_threads knob (GPU parallelism is
# implicit in the SYCL kernel), so this is not just a device= variant of
# quant_dequant_roundtrip() above — it calls a structurally simpler API.

def _xpu_ready() -> bool:
    return kvweave_quant_xpu is not None and hasattr(torch, "xpu") and torch.xpu.is_available()


requires_xpu = pytest.mark.skipif(
    not _xpu_ready(),
    reason="kvweave_quant_xpu not built (KVWEAVE_XPU=1) or no XPU device available",
)


def quant_dequant_roundtrip_xpu(
    tensor: torch.Tensor,
    cfg: dict,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Quantize then dequantize on XPU, returning (quantized, restored)."""
    src = tensor.to("xpu")
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
    restored = kvweave_quant_xpu.dequantize_kvcache(
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
        tensor.dtype,
        cfg["signs"],
        cfg["perm"],
    )
    return quantized, restored


# ---------------------------------------------------------------------------
# Fused API helpers
# ---------------------------------------------------------------------------

def build_kvw2_header(
    chunk: torch.Tensor,
    cfg: dict,
) -> bytes:
    """Build binary KVW2 header for kvweave_serialize_chunk."""
    chunk_tokens, _, h_merged = chunk.shape
    scaling_to_int = {"per_tensor": 0, "per_token": 1, "per_channel": 2}
    header = struct.pack(
        ">4sBBBBBBB",
        b"KVW2",
        cfg["qbit"],
        int(cfg["rh"]),
        int(cfg["asym"]),
        int(cfg["precond"]),
        3,  # ndim for [T, 2, H*D]
        1,  # MemoryFormat.KV_T2D
        scaling_to_int.get(cfg["scaling_method"], 1),
    )
    if cfg["precond"] and cfg["signs"] is not None:
        header += struct.pack(">I", cfg["signs"].numel())
        header += cfg["signs"].contiguous().numpy().tobytes()
        header += cfg["perm"].contiguous().numpy().tobytes()
    header += struct.pack(">iii", chunk_tokens, 2, h_merged)
    return header


def prepare_fused_inputs(
    chunk: torch.Tensor,
    cfg: dict,
) -> Tuple[torch.Tensor, bytes]:
    """Convert 3D [T, 2, H*D] chunk to fused API inputs: (tensor_4d, header)."""
    tensor_4d = chunk.permute(1, 0, 2).unsqueeze(1).contiguous()
    header = build_kvw2_header(chunk, cfg)
    return tensor_4d, header


def split_kvw2_payload(payload: bytes, kv_size: int = 2) -> Tuple[List[bytes], bytes]:
    """Parse fused payload: extract scale blobs and quantized data."""
    buf = memoryview(payload)
    if bytes(buf[:4]) != b"KVW2":
        raise ValueError("fused payload does not start with KVW2")
    _qbit, _rh, _asym, precond, ndim, _fmt, _scaling = struct.unpack(
        ">BBBBBBB", bytes(buf[4:11])
    )
    offset = 11
    if precond:
        h = struct.unpack(">I", bytes(buf[offset:offset + 4]))[0]
        offset += 4 + 4 * h + 4 * h  # signs + perm
    offset += 4 * ndim  # shape dims

    scale_blobs: List[bytes] = []
    for _ in range(kv_size):
        scale_len = struct.unpack(">I", bytes(buf[offset:offset + 4]))[0]
        offset += 4
        scale_blobs.append(bytes(buf[offset:offset + scale_len]))
        offset += scale_len
    return scale_blobs, bytes(buf[offset:])


# ---------------------------------------------------------------------------
# Performance benchmark utilities
# ---------------------------------------------------------------------------

@dataclass
class BenchResult:
    stage: str
    iters: int
    data_bytes: int
    avg_ms: float
    min_ms: float
    max_ms: float
    p50_ms: float
    p95_ms: float
    throughput_GBps: float
    extra: dict = field(default_factory=dict)


def bench(fn: Callable, warmup: int, iters: int, data_bytes: int, stage: str) -> BenchResult:
    """Run fn() for warmup + iters iterations and return timing statistics."""
    for _ in range(warmup):
        fn()

    durations: List[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        durations.append((t1 - t0) * 1e3)

    arr = np.array(durations)
    avg_ms = float(arr.mean())
    throughput = (data_bytes / (avg_ms * 1e-3)) / 1e9 if avg_ms > 0 else 0.0
    return BenchResult(
        stage=stage,
        iters=iters,
        data_bytes=data_bytes,
        avg_ms=avg_ms,
        min_ms=float(arr.min()),
        max_ms=float(arr.max()),
        p50_ms=float(np.percentile(arr, 50)),
        p95_ms=float(np.percentile(arr, 95)),
        throughput_GBps=throughput,
    )


def print_bench_result(r: BenchResult) -> None:
    """Print a single bench result as a formatted line."""
    data_mb = r.data_bytes / 1e6
    print(
        f"PERF | {r.stage:<22} "
        f"data={data_mb:.2f}MB  "
        f"avg={r.avg_ms:.3f}ms  "
        f"p50={r.p50_ms:.3f}ms  "
        f"p95={r.p95_ms:.3f}ms  "
        f"throughput={r.throughput_GBps:.3f} GB/s"
    )


@pytest.fixture(scope="session")
def perf_collector():
    """Collect performance results across the session, write JSON at end."""
    results = []
    yield results
    if results:
        out_path = Path(__file__).parent / "perf_results.json"
        with open(out_path, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        print(f"\n[perf] Results written to {out_path}")
