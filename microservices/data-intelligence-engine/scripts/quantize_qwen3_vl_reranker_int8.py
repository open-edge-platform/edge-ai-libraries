#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Weight-only INT8 quantization for the exported Qwen3-VL-Reranker OV IRs.

Uses NNCF compress_weights (INT8_ASYM, per-channel; NNCF 3.x does not
allow group-wise overrides for INT8 modes) on each modality graph
(text/image/video) and writes a sibling model directory. FP16 IRs are left
untouched. The output directory keeps the engine's serving convention
(<model-id-last-component>-OV), so ENGINE_MEDIA_RERANK_MODEL_ID picks it up
as Qwen/Qwen3-VL-Reranker-2B-INT8. Usage:

    python quantize_qwen3_vl_reranker_int8.py \
        --src data-intelligence-engine/workspace/models/Qwen3-VL-Reranker-2B-OV \
        --dst data-intelligence-engine/workspace/models/Qwen3-VL-Reranker-2B-INT8-OV
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

import nncf
import openvino as ov
from nncf.parameters import CompressWeightsMode

IRS = ("reranker_text", "reranker_image", "reranker_video")
# Files copied verbatim so the INT8 dir is a drop-in model directory.
COPY_FILES = (
    "1_LogitScore",
    "added_tokens.json",
    "additional_chat_templates",
    "chat_template.jinja",
    "config.json",
    "export_shapes.json",
    "merges.txt",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "video_preprocessor_config.json",
    "vocab.json",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--dst", type=Path, required=True)
    parser.add_argument("--group-size", type=int, default=-1,
                        help="INT8 modes require per-channel (-1); group-wise "
                             "only applies to INT4 modes")
    parser.add_argument("--mode", default="INT8_ASYM",
                        choices=("INT8_ASYM", "INT8_SYM"))
    args = parser.parse_args()

    if args.dst.resolve() == args.src.resolve():
        sys.exit("error: --dst must differ from --src; FP16 IRs are never overwritten")
    args.dst.mkdir(parents=True, exist_ok=True)

    core = ov.Core()
    mode = getattr(CompressWeightsMode, args.mode)
    for name in IRS:
        xml = args.src / f"{name}.xml"
        if not xml.exists():
            sys.exit(f"error: missing {xml}")
        started = time.perf_counter()
        model = core.read_model(xml)
        compressed = nncf.compress_weights(
            model, mode=mode, group_size=args.group_size)
        ov.save_model(compressed, args.dst / f"{name}.xml")
        size_mb = (args.dst / f"{name}.bin").stat().st_size / 1e6
        print(f"{name}: {size_mb:.0f} MB bin, "
              f"{time.perf_counter() - started:.0f}s", flush=True)

    for rel in COPY_FILES:
        src_file = args.src / rel
        if src_file.is_dir():
            shutil.copytree(src_file, args.dst / rel, dirs_exist_ok=True)
        elif src_file.exists():
            shutil.copy2(src_file, args.dst / rel)
    print(f"done -> {args.dst}")


if __name__ == "__main__":
    main()
