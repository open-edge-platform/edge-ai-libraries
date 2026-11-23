# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tiny file-only video packages; encoder placeholders must never be compiled."""

import json


VIDEO_FAMILIES = ("viclip-b", "viclip-l", "cosmos-224p")
_SPECS = {
    "viclip-b": ("OpenGVLab/ViCLIP-B-16-hf", "viclip", 512, 32, "clip_bpe"),
    "viclip-l": ("OpenGVLab/ViCLIP-L-14-hf", "viclip", 768, 32, "clip_bpe"),
    "cosmos-224p": ("nvidia/Cosmos-Embed1-224p", "cosmos", 256, 128, "bert"),
}


def video_package(root, name=None, *, family="viclip-b", precision="fp16", ir=True):
    """Write a package satisfying production's file/metadata preflight contract."""
    model_id, preprocessing, dimension, context_length, tokenizer_type = _SPECS[family]
    path = root / (name or f"{family}-{precision}")
    path.mkdir(parents=True)
    tokenizer = {
        "tokenizer_config.json": json.dumps({
            "tokenizer_class": "CLIPTokenizer" if tokenizer_type == "clip_bpe" else "BertTokenizer",
            "model_max_length": context_length,
        }),
        "special_tokens_map.json": "{}",
    }
    if tokenizer_type == "clip_bpe":
        tokenizer.update({
            "vocab.json": '{"<|startoftext|>": 0, "<|endoftext|>": 1}',
            "merges.txt": "#version: 0.2\n",
        })
    else:
        tokenizer["vocab.txt"] = "[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\n"
    for filename, content in tokenizer.items():
        (path / filename).write_text(content, encoding="utf-8")
    artifacts = {
        "video_encoder": ["video_encoder.xml", "video_encoder.bin"],
        "text_encoder": ["text_encoder.xml", "text_encoder.bin"],
        "tokenizer": list(tokenizer),
    }
    if ir:
        for tower in ("video_encoder", "text_encoder"):
            (path / f"{tower}.xml").write_text("<xml/>", encoding="utf-8")
            (path / f"{tower}.bin").write_bytes(b"\x00")
    metadata = {
        "format": 1,
        "name": family,
        "model_id": model_id,
        "frames": 8,
        "image_size": 224,
        "context_length": context_length,
        "dimension": dimension,
        "precision": precision,
        "preprocessing": preprocessing,
        "tokenizer_type": tokenizer_type,
        "parameter_count": 1,
        "artifacts": artifacts,
    }
    (path / "video_embedding.json").write_text(json.dumps(metadata), encoding="utf-8")
    return path