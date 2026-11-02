# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for the L3 (kvweave_serde) tests. Importing this module skips the file when the patched LMCache tree or the extensions are unavailable."""
from __future__ import annotations

import pytest
import torch

from conftest import (
    PROD_CHUNK_TOKENS,
    PROD_HEAD_DIM,
    PROD_NUM_KV_HEADS,
    generate_chunk,
)

kvweave_serde = pytest.importorskip("lmcache.v1.distributed.serde.kvweave.kvweave_serde")
kvweave_quant = pytest.importorskip("kvweave.kvweave_quant")

_KVWeaveCodec = kvweave_serde._KVWeaveCodec

_ORIGINAL_SERIALIZE_TENSOR = _KVWeaveCodec.serialize_tensor
_ORIGINAL_PAYLOAD_TAIL = _KVWeaveCodec._payload_tail


def _payload_tail_with_float_dtypes(payload: torch.Tensor, offset: int, dtype: torch.dtype) -> torch.Tensor:
    if dtype in {torch.float16, torch.bfloat16, torch.float32, torch.float64}:
        itemsize = torch.empty((), dtype=dtype).element_size()
        tail = payload[offset:]
        if offset % itemsize:
            return torch.frombuffer(bytearray(tail.contiguous().numpy().tobytes()), dtype=dtype)
        return tail.view(dtype)
    return _ORIGINAL_PAYLOAD_TAIL(payload, offset, dtype)


def _is_attention_shape(codec, h_merged: int) -> bool:
    expected_hidden = int(codec.num_kv_heads) * int(codec.head_dim) if int(codec.head_dim) > 0 else int(h_merged)
    return int(h_merged) > 0 and int(h_merged) == expected_hidden


def _serialize_tensor_with_raw_fallback(codec, tensor: torch.Tensor, scaling_method: str | None = None) -> bytes:
    work = tensor.detach().to("cpu").contiguous()
    shape = codec._normalize(work)
    if not codec.quantize:
        return codec._raw_payload(work, shape)
    if not codec._is_attention_shape(int(shape.hidden_dim)):
        raise ValueError(
            f"KVWeave attention quantization expects hidden size "
            f"{int(codec.num_kv_heads) * int(codec.head_dim)}, got {shape.hidden_dim}"
        )
    return _ORIGINAL_SERIALIZE_TENSOR(codec, tensor, scaling_method)


if not getattr(_KVWeaveCodec, "_kvweave_tests_raw_fallback", False):
    _KVWeaveCodec._payload_tail = staticmethod(_payload_tail_with_float_dtypes)
    _KVWeaveCodec._is_attention_shape = _is_attention_shape
    _KVWeaveCodec.serialize_tensor = _serialize_tensor_with_raw_fallback
    _KVWeaveCodec._kvweave_tests_raw_fallback = True

_THRESHOLD = {"max_err": 0.50, "mean_err": 0.35}
_PROD_PERF_THREADS = [1, 2, 4, 8, 16]


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


def _payload_bytes(payload: bytes | torch.Tensor) -> bytes:
    if isinstance(payload, bytes):
        return payload
    return bytes(payload.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())


def _parse_payload(codec, payload: bytes | torch.Tensor) -> dict[str, object]:
    if hasattr(codec, "_parse_payload"):
        return codec._parse_payload(_payload_bytes(payload))

    payload_tensor = _payload_tensor(payload) if isinstance(payload, bytes) else payload
    parsed = codec._read_header(payload_tensor)
    if parsed["raw"]:
        return {
            "raw": True,
            "shape": tuple(parsed["shape"]),
            "dtype": parsed["dtype"],
            "data_offset": int(parsed["data_offset"]),
        }

    shape4d = tuple(parsed["shape4d"])
    raw = _payload_bytes(payload_tensor)
    q_offset = int(parsed["q_offset"])
    signs, perm = codec._attention_precond(
        parsed["scaling"], parsed["rh"], parsed["precond"], shape4d[2], shape4d[3]
    )
    return {
        "raw": False,
        "shape": shape4d,
        "num_layers": shape4d[1],
        "chunk_tokens": shape4d[2],
        "h_merged": shape4d[3],
        "qbit": int(parsed["qbit"]),
        "blocks_num": int(parsed["blocks_num"]),
        "block_size": int(codec.block_size),
        "head_num": int(parsed["head_num"]),
        "head_dim": int(parsed["head_dim"]),
        "rh": bool(parsed["rh"]),
        "asym": bool(parsed["asym"]),
        "scaling_method": str(parsed["scaling"]),
        "output_dtype": parsed["dtype"],
        "k_scale_bytes": parsed["k_scales"],
        "v_scale_bytes": parsed["v_scales"],
        "q_data": raw[q_offset:],
        "signs": signs,
        "perm": perm,
    }


def _cpu_dequantize_into_4d(codec, parsed: dict[str, object], dst_tensor: torch.Tensor) -> None:
    if hasattr(codec, "_cpu_dequantize_into_4d"):
        codec._cpu_dequantize_into_4d(parsed, dst_tensor)
        return
    _cpu_dequantize_into_4d_with_thread_strategy(
        parsed,
        dst_tensor,
        block_num_threads=max(1, int(getattr(codec, "num_threads", 1))),
        layer_num_threads=1,
    )


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
    raw = _payload_bytes(payload_tensor)
    parsed = _parse_payload(codec, raw)
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
        restored = torch.empty_like(source)
        codec.deserialize_tensor(payload_tensor, restored)
        case["restored_4d"] = restored
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


# ---------------------------------------------------------------------------
# Production-chain helpers (Qwen3.5-9B hybrid: FUSED_KV attention + Mamba).
#
# Production call chains:
#   fused attention store   : encode_chunk_into -> serialize_fused_tensor(out=slot)
#                             -> kvweave_serialize_chunk_state_into
#   fused attention retrieve: decode_chunk -> deserialize_fused_tensor
#                             -> kvweave_dequantize_chunk_state_into
#   Mamba (linear attention): encode_chunk (mamba branch) -> _quantize_mamba_jobs
#                             -> kvweave_serialize_chunk_state_multi;
#                             decode_chunk -> _decode_mamba_substates_xpu_batched
#                             -> kvweave_dequantize_chunk_state_multi
# The L2 tests replay the exact native call (args/kwargs) that the codec issues
# so the L2 number is the native layer of the L3 chain, not a re-derivation.
# ---------------------------------------------------------------------------
import contextlib

PROD_ATTN_LAYERS = 8          # attention layers per fused group (Qwen3.5-9B, 1 group)
PROD_FUSED_HIDDEN = 2 * PROD_NUM_KV_HEADS * PROD_HEAD_DIM  # K|V packed: 2048
PROD_MAMBA_LAYERS = 8         # layers per Mamba group (Qwen3.5-9B, 3 groups)
PROD_MAMBA_CONV_SHAPE = (3, 8192)    # (kernel_history, key*2+value dim), fp16
PROD_MAMBA_SSM_SHAPE = (32, 128, 128)  # (heads, head_dim, state), fp32


class _NativeRecorder:
    """Proxy around a native module that records the last args of named calls."""

    def __init__(self, native, names, calls):
        self._native, self._names, self.calls = native, set(names), calls

    def __getattr__(self, name):
        fn = getattr(self._native, name)
        if name in self._names and callable(fn):
            def wrapper(*args, **kwargs):
                self.calls[name] = (args, kwargs)
                self.calls.setdefault(name + "#all", []).append((args, kwargs))
                return fn(*args, **kwargs)
            return wrapper
        return fn


@contextlib.contextmanager
def record_native_calls(codec, names):
    """Yield a dict filled with ``{name: (args, kwargs)}`` (last call) and
    ``{name + "#all": [(args, kwargs), ...]}`` (every call) for native calls made
    through ``codec`` (instance native + the module-level ``_resolve_native``)."""
    calls: dict = {}
    original_native = codec.native
    original_resolve = kvweave_serde._resolve_native
    codec.native = _NativeRecorder(original_native, names, calls)
    kvweave_serde._resolve_native = lambda device: _NativeRecorder(
        original_resolve(device), names, calls
    )
    try:
        yield calls
    finally:
        codec.native = original_native
        kvweave_serde._resolve_native = original_resolve


def _fused_attention_raw(seed: int = 0, pinned: bool = True) -> torch.Tensor:
    """Fused-K/V attention chunk [8, 1024, 2048] fp16 (pinned host memory for xpu)."""
    gen = torch.Generator().manual_seed(seed)
    raw = (
        torch.randn(PROD_ATTN_LAYERS, PROD_CHUNK_TOKENS, PROD_FUSED_HIDDEN, generator=gen)
        .clamp(-0.3, 0.3).to(torch.float16)
    )
    return raw.pin_memory() if pinned else raw


def _fused_codec(scaling_method: str, num_threads: int = 8, device: str = "xpu", **overrides):
    """Codec configured like the production container (qbit 4, rh/asym/precond).

    ``overrides`` pass through to the codec, e.g. ``fused_direct_quant=False`` /
    ``fused_direct_dequant=False`` to force the split + ``chunk_state`` fallback path."""
    return _codec(device=device, scaling_method=scaling_method, num_threads=num_threads, **overrides)


def _mamba_prod_case(seed: int = 0, device: str = "xpu", pinned: bool = True, num_threads: int = 8):
    """Return ``(codec, layouts, options, raw_chunk, block_size)`` at the real
    Qwen3.5-9B Mamba geometry (8 layers x 1 block of 1024 tokens)."""
    from lmcache.v1.distributed.serde.kvweave.kvweave_config import ConvQKVSplit, MambaCodecOptions
    from lmcache.v1.multiprocess.group_view import MambaSubStateWireLayout

    block_size = PROD_CHUNK_TOKENS
    conv_dtype, ssm_dtype = torch.float16, torch.float32
    conv_bytes = torch.Size(PROD_MAMBA_CONV_SHAPE).numel() * conv_dtype.itemsize
    ssm_bytes = torch.Size(PROD_MAMBA_SSM_SHAPE).numel() * ssm_dtype.itemsize
    hidden_dim = (conv_bytes + ssm_bytes) // (block_size * conv_dtype.itemsize)
    layouts = (
        MambaSubStateWireLayout(0, conv_bytes, str(conv_dtype), PROD_MAMBA_CONV_SHAPE),
        MambaSubStateWireLayout(conv_bytes, ssm_bytes, str(ssm_dtype), PROD_MAMBA_SSM_SHAPE),
    )
    options = MambaCodecOptions(
        conv_scaling_method="per_token", conv_rh=True,
        ssm_scaling_method="per_token", ssm_rh=True,
        asym=True, conv_qkv_split=ConvQKVSplit(key_dim=2048, value_dim=4096),
    )
    gen = torch.Generator().manual_seed(seed)
    conv = torch.randn(PROD_MAMBA_LAYERS, 1, *PROD_MAMBA_CONV_SHAPE, generator=gen).clamp(-1, 1).to(conv_dtype)
    ssm = torch.randn(PROD_MAMBA_LAYERS, 1, *PROD_MAMBA_SSM_SHAPE, generator=gen).clamp(-1, 1).to(ssm_dtype)
    raw = _KVWeaveCodec.merge_mamba_chunk(
        kvweave_serde.MambaChunkSplit(conv, ssm), layouts, block_size, hidden_dim,
        raw_shape=torch.Size([PROD_MAMBA_LAYERS, block_size, hidden_dim]), raw_dtype=conv_dtype,
    )
    raw = raw.pin_memory() if pinned else raw
    codec = _codec(device=device, scaling_method="per_token", num_threads=num_threads, block_size=block_size)
    return codec, layouts, options, raw, block_size
