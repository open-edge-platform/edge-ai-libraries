# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for the L3 (kvweave_serde) test files.

Extracted from the former test_kvweave_serde.py so both test_l3_serde_accuracy.py
and test_l3_serde_perf.py can reuse the codec factory, attention-chunk builders,
and deserialize-case setup without duplication.

``kvweave_serde`` ships inside the patched LMCache tree (applied from
integration/lmcache/patches/), not as a top-level module of this package.
Importing it here triggers ``pytest.importorskip`` for kvweave_serde /
kvweave_quant, so any L3 test file that imports it is automatically skipped
when a patched LMCache checkout / the extensions are unavailable.
"""
from __future__ import annotations

import pytest
import torch

from conftest import (
    PROD_CHUNK_TOKENS,
    PROD_HEAD_DIM,
    PROD_NUM_KV_HEADS,
    generate_chunk,
)

kvweave_serde = pytest.importorskip("lmcache.v1.distributed.serde.kvweave_serde")
kvweave_quant = pytest.importorskip("kvweave.kvweave_quant")

_KVWeaveCodec = kvweave_serde._KVWeaveCodec
_copy_bytes_to_tensor = kvweave_serde._copy_bytes_to_tensor

_THRESHOLD = {"max_err": 0.50, "mean_err": 0.35}
_PROD_PERF_THREADS = [1, 2, 4, 8, 16]
# Representative subset of the (thread-placement x scaling-scenario) grid for
# the full-depth (PROD_NUM_LAYERS) multilayer deserialize sweep: one
# thread-placement strategy per axis (block-parallel vs layer-parallel) at a
# representative thread count, crossed with a preconditioned and a
# non-preconditioned scaling scenario.
_PROD_THREAD_STRATEGIES = [
    ("block_t8", 8, 1),
    ("layer_t8", 1, 8),
]
_PROD_THREAD_SCENARIOS = [
    ("per_channel_rh", "per_channel", True),
    ("per_tensor_no_rh", "per_tensor", False),
]


def _codec(**overrides):
    kwargs = {
        "quantize": True,
        "qbit": 4,
        "scaling_method": "per_channel",
        "rh": True,
        "asym": True,
        "precond": True,
        "num_threads": 1,
        "num_kv_heads": PROD_NUM_KV_HEADS,
        "head_dim": PROD_HEAD_DIM,
    }
    kwargs.update(overrides)
    return _KVWeaveCodec(kwargs)


def _attention_chunk_3d(
    *,
    chunk_tokens: int = PROD_CHUNK_TOKENS,
    seed: int = 0,
    dtype: torch.dtype = torch.float16,
) -> torch.Tensor:
    return generate_chunk(
        chunk_tokens=chunk_tokens,
        head_num=PROD_NUM_KV_HEADS,
        head_dim=PROD_HEAD_DIM,
        dtype=dtype,
        seed=seed,
    )


def _attention_chunk_4d(
    *,
    chunk_tokens: int = PROD_CHUNK_TOKENS,
    num_layers: int = 1,
    seed: int = 0,
    dtype: torch.dtype = torch.float16,
) -> torch.Tensor:
    layers = [
        _attention_chunk_3d(
            chunk_tokens=chunk_tokens,
            seed=seed + layer,
            dtype=dtype,
        ).permute(1, 0, 2)
        for layer in range(num_layers)
    ]
    return torch.stack(layers, dim=1).contiguous()


def _payload_tensor(payload: bytes) -> torch.Tensor:
    return torch.frombuffer(bytearray(payload), dtype=torch.uint8)


def _prepare_deserialize_case_4d(
    num_threads: int,
    *,
    seed: int = 21,
    num_layers: int = 1,
    chunk_tokens: int = PROD_CHUNK_TOKENS,
    scaling_method: str = "per_channel",
    rh: bool = True,
    include_restored_4d: bool = True,
) -> dict[str, object]:
    codec = _codec(
        num_threads=num_threads,
        scaling_method=scaling_method,
        rh=rh,
        precond=rh,
    )
    source = _attention_chunk_4d(
        chunk_tokens=chunk_tokens,
        num_layers=num_layers,
        seed=seed,
    )
    payload = codec.serialize_tensor(source)
    payload_tensor = _payload_tensor(payload)
    dst = torch.empty_like(source)
    raw = kvweave_serde._tensor_to_bytes(payload_tensor)
    parsed = codec._parse_payload(raw)
    q_dtype = torch.int8 if int(parsed["qbit"]) <= 8 else torch.int16
    q_data = torch.frombuffer(bytearray(parsed["q_data"]), dtype=q_dtype)
    case = {
        "codec": codec,
        "source": source,
        "payload_tensor": payload_tensor,
        "dst": dst,
        "raw": raw,
        "parsed": parsed,
        "q_dtype": q_dtype,
        "q_data": q_data,
    }
    if include_restored_4d:
        case["restored_4d"] = kvweave_serde._KVWeaveCodec._cpu_dequantize(codec, parsed)
    return case


def _cpu_dequantize_into_4d_with_thread_strategy(
    parsed: dict[str, object],
    dst_tensor: torch.Tensor,
    *,
    block_num_threads: int,
    layer_num_threads: int,
) -> None:
    if block_num_threads < 1 or layer_num_threads < 1:
        raise ValueError("block_num_threads and layer_num_threads must both be >= 1")

    qbit = int(parsed["qbit"])
    q_dtype = torch.int8 if qbit <= 8 else torch.int16
    q_data = torch.frombuffer(bytearray(parsed["q_data"]), dtype=q_dtype)
    kvweave_quant.kvweave_dequantize_chunk_into_4d(
        q_data,
        parsed["k_scale_bytes"],
        parsed["v_scale_bytes"],
        dst_tensor,
        int(parsed["num_layers"]),
        int(parsed["chunk_tokens"]),
        int(parsed["h_merged"]),
        qbit=qbit,
        blocks_num=int(parsed["blocks_num"]),
        block_size=int(parsed["block_size"]),
        head_num=int(parsed["head_num"]),
        head_dim=int(parsed["head_dim"]),
        rh=bool(parsed["rh"]),
        asym=bool(parsed["asym"]),
        scaling_method=str(parsed["scaling_method"]),
        output_dtype=parsed["output_dtype"],
        signs=parsed["signs"],
        perm=parsed["perm"],
        num_threads=block_num_threads,
        layer_num_threads=layer_num_threads,
    )


def _assert_close_to_source(restored: torch.Tensor, source: torch.Tensor) -> None:
    diff = (restored.float() - source.float()).abs()
    max_err = diff.max().item()
    mean_err = diff.mean().item()
    print(f"ACC | kvweave_serde max_err={max_err:.6f} mean_err={mean_err:.6f}")
    assert max_err < _THRESHOLD["max_err"]
    assert mean_err < _THRESHOLD["mean_err"]
