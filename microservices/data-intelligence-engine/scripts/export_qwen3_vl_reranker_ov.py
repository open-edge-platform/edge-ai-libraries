#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Export the official Qwen3-VL-Reranker-2B checkpoint to OpenVINO.

Export one forward-only OpenVINO graph per mode. The graphs are independently
compiled on first use by the engine.

Run check_qwen3_vl_reranker_parity.py against representative
examples before serving.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_INPUTS = {
    "text": ("input_ids",),
    "image": ("input_ids", "pixel_values", "image_grid_thw", "position_ids"),
    "video": (
        "input_ids", "attention_mask", "pixel_values_videos", "video_grid_thw",
        "position_ids",
    ),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="local official Qwen/Qwen3-VL-Reranker-2B checkpoint")
    parser.add_argument("--output", type=Path, required=True,
                        help="OV package directory")
    parser.add_argument("--mode", choices=_INPUTS, required=True)
    parser.add_argument("--sample", type=Path,
                        help="local image/video fixture for the selected mode")
    parser.add_argument("--query", default="Find the relevant item")
    parser.add_argument("--text", default="The relevant item appears here")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--seq-bucket", type=int, default=768,
                        help="video mode pads the token axis to this fixed length, "
                             "so every video query shares one compiled graph")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.mode != "text" and (args.sample is None or not args.sample.is_file()):
        parser.error("--sample must point to a local media file for image/video")
    if args.frames < 1 or args.seq_bucket < 1:
        parser.error("--frames and --seq-bucket must be positive")
    source = args.source.resolve()
    if not source.is_dir():
        parser.error("--source must be a local checkpoint directory")
    config_path = source / "config.json"
    score_path = source / "1_LogitScore" / "config.json"
    reference_script = source / "scripts" / "qwen3_vl_reranker.py"
    if not all(path.is_file() for path in (config_path, score_path, reference_script)):
        parser.error("source lacks official config, 1_LogitScore config, or reference script")
    config = json.loads(config_path.read_text())
    scores = json.loads(score_path.read_text())
    if config.get("architectures") != ["Qwen3VLForConditionalGeneration"]:
        parser.error("source is not a Qwen3-VL conditional-generation checkpoint")
    if (scores.get("true_token_id"), scores.get("false_token_id")) != (9693, 2152):
        parser.error("source has unexpected Reranker yes/no token IDs")
    out = args.output.resolve()
    ir_path = out / f"reranker_{args.mode}.xml"
    if ir_path.exists() and not args.overwrite:
        parser.error(f"{ir_path} exists; pass --overwrite to replace it")

    import numpy as np
    import openvino as ov
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    from inference.multimodal.qwen3_vl_reranker_inputs import (
        VISUAL_SIZE, encode, pad_frames, pad_pair, rope_position_ids,
    )

    processor = AutoProcessor.from_pretrained(
        str(source), trust_remote_code=True, padding_side="left"
    )
    processor.tokenizer.padding_side = "left"
    if args.mode == "text":
        document = {"text": args.text}
    elif args.mode == "image":
        from PIL import Image

        with Image.open(args.sample) as image:
            document = {"image": image.convert("RGB")}
    else:
        from core.multimodal.frames import sample_frames

        document = {"video": pad_frames(sample_frames(str(args.sample), args.frames), args.frames)}
    encoded = encode(processor, args.query, document)
    if args.mode != "text":
        encoded["position_ids"] = rope_position_ids(encoded, config)
    if args.mode == "video":
        # Trace the canonical padded shape: every runtime video pair is padded
        # to the same bucket, so the Intel GPU compiler sees one shape ever.
        encoded, encoded["position_ids"] = pad_pair(
            encoded, encoded["position_ids"], args.seq_bucket,
            processor.tokenizer.pad_token_id,
        )
    names = _INPUTS[args.mode]
    missing = set(names) - encoded.keys()
    if missing:
        raise ValueError(f"processor did not produce required inputs: {sorted(missing)}")
    example = tuple(torch.from_numpy(np.asarray(encoded[name])) for name in names)

    print("Loading official Reranker weights for offline conversion...", flush=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        str(source), dtype=torch.float16, attn_implementation="eager",
        low_cpu_mem_usage=True,
    ).eval()

    # Transformers' generic mask builder uses torch.vmap during tracing, which
    # TorchScript cannot capture here (unordered_map::at). The equivalent
    # triangular additive mask is traceable; for the padded video bucket the
    # attention mask additionally removes pad tokens from every key position.
    from transformers.models.qwen3_vl import modeling_qwen3_vl

    def causal_mask_for_single_pair(
        config, input_embeds, attention_mask, cache_position,
        past_key_values, position_ids,
    ):
        length = input_embeds.shape[1]
        positions = torch.arange(length, device=input_embeds.device)
        hidden = positions[None, :] > positions[:, None]
        mask = torch.zeros(
            (length, length), dtype=input_embeds.dtype, device=input_embeds.device
        ).masked_fill(hidden, torch.finfo(input_embeds.dtype).min)
        if attention_mask is not None:
            # Pad key positions get +min, i.e. excluded from every query row.
            # attention_mask is [batch=1, key_len]; use its key axis directly.
            pad = attention_mask.to(torch.bool)[0]
            mask = mask.masked_fill(~pad[None, :], torch.finfo(input_embeds.dtype).min)
        return mask[None, None]

    modeling_qwen3_vl.create_causal_mask = causal_mask_for_single_pair

    class ForwardOnly(torch.nn.Module):
        def __init__(self, checkpoint):
            super().__init__()
            self.checkpoint = checkpoint

        def forward(self, *inputs):
            values = dict(zip(names, inputs))
            # One forward pass only. No generation loop, KV cache, or sequence
            # classification head: score the yes/no vocabulary logits directly.
            return self.checkpoint(
                **values, use_cache=False, logits_to_keep=1,
            ).logits

    with torch.no_grad():
        graph = ov.convert_model(ForwardOnly(model).eval(), example_input=example)
    if len(graph.inputs) != len(names):
        raise RuntimeError(
            f"export kept {len(graph.inputs)} inputs, expected {len(names)}; "
            "inspect the traced graph before using it"
        )
    if len(graph.outputs) != 1:
        raise RuntimeError("export must have exactly one logits output")
    for port, name in zip(graph.inputs, names):
        port.get_tensor().set_names({name})
    graph.outputs[0].get_tensor().set_names({"logits"})
    shape = graph.outputs[0].partial_shape
    if shape.rank.is_static and shape.rank.get_length() != 3:
        raise RuntimeError(f"unexpected logits rank: {shape}")

    out.mkdir(parents=True, exist_ok=True)
    stage = out / f".reranker_{args.mode}_export"
    stage.mkdir(exist_ok=True)
    staged_ir = stage / ir_path.name
    ov.save_model(graph, staged_ir, compress_to_fp16=True)
    for suffix in (".xml", ".bin"):
        (stage / f"reranker_{args.mode}{suffix}").replace(
            out / f"reranker_{args.mode}{suffix}"
        )
    stage.rmdir()
    processor.save_pretrained(str(out))
    shutil.copy2(config_path, out / "config.json")
    score_dest = out / "1_LogitScore"
    score_dest.mkdir(exist_ok=True)
    shutil.copy2(score_path, score_dest / "config.json")
    manifest_path = out / "export_shapes.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"modes": {}}
    manifest["visual_size"] = list(VISUAL_SIZE)
    if args.mode == "video":
        manifest["video_seq_bucket"] = args.seq_bucket
        manifest["video_frames"] = args.frames
    manifest["modes"][args.mode] = {
        key: np.asarray(encoded[key]).tolist()
        for key in ("image_grid_thw", "video_grid_thw") if key in encoded
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Exported {ir_path}. Run the parity checker before using it.")


if __name__ == "__main__":
    main()
