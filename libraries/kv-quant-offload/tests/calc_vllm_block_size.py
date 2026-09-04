#!/usr/bin/env python3
"""Report the hybrid KV-cache block size selected by this vLLM build.

Example matching an API-server launch:
    python auto.py /llm/models/Qwen3.5-35B-A3B \
        --dtype float16 --tp-size 1 --block-size 1024 --ma-mode align \
        --enable-prefix-caching
"""

import argparse
from pathlib import Path


def get_vllm_config(args: argparse.Namespace):
    try:
        from vllm.engine.arg_utils import EngineArgs
    except ImportError as error:
        raise RuntimeError(
            "This script requires the vLLM Python environment"
        ) from error

    engine_args = EngineArgs(
        model=str(args.model_dir),
        dtype=args.dtype,
        tensor_parallel_size=args.tp_size,
        block_size=args.block_size,
        enable_prefix_caching=args.enable_prefix_caching,
        mamba_cache_mode=args.ma_mode,
        mamba_ssm_cache_dtype=args.mamba_ssm_cache_dtype,
    )
    return engine_args.create_engine_config()


def update_hybrid_block_size(vllm_config) -> None:
    """Invoke the same vLLM function used after model loading on XPU."""
    from vllm.platforms import current_platform
    from vllm.v1.attention.backends.flash_attn import FlashAttentionBackend

    current_platform._align_hybrid_block_size(
        vllm_config,
        FlashAttentionBackend,
    )
    if current_platform.device_type != "xpu":
        return

    layer_types = vllm_config.model_config.hf_text_config.layer_types
    if "linear_attention" not in layer_types:
        return

    # Mirror XPUPlatform.update_block_size_for_backend's GDN post-processing.
    cache_config = vllm_config.cache_config
    new_block_size = 1 << (max(cache_config.block_size, 64) - 1).bit_length()
    if new_block_size == cache_config.block_size:
        return
    if cache_config.mamba_cache_mode == "align":
        cache_config.mamba_block_size = new_block_size
    if cache_config.mamba_page_size_padded is not None:
        attn_page_size_per_token = (
            cache_config.mamba_page_size_padded // cache_config.block_size
        )
        cache_config.mamba_page_size_padded = (
            new_block_size * attn_page_size_per_token
        )
    cache_config.block_size = new_block_size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--tp-size", type=int, default=1)
    parser.add_argument("--ma-mode", choices=("none", "align", "all"), default="align")
    parser.add_argument("--mamba-ssm-cache-dtype", default="auto")
    parser.add_argument("--enable-prefix-caching", action="store_true")
    parser.add_argument("--chunk-multiplier", type=int, default=1)
    args = parser.parse_args()

    vllm_config = get_vllm_config(args)
    cache_config = vllm_config.cache_config
    initial_block_size = cache_config.block_size
    update_hybrid_block_size(vllm_config)

    block_size = cache_config.block_size
    chunk_size = block_size * args.chunk_multiplier
    print(f"model                  : {args.model_dir}")
    print(f"model type             : {vllm_config.model_config.hf_text_config.model_type}")
    print(f"dtype                  : {vllm_config.model_config.dtype}")
    print(f"mamba SSM cache dtype  : {cache_config.mamba_ssm_cache_dtype}")
    print(f"mamba cache mode       : {cache_config.mamba_cache_mode}")
    print(f"requested block size   : {initial_block_size} tokens")
    print(f"vLLM block size        : {block_size} tokens")
    print(f"LMCache chunk size     : {chunk_size} tokens")
    print(f"chunk size % block     : {chunk_size % block_size}")


if __name__ == "__main__":
    main()
