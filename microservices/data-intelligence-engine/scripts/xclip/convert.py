# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Export X-CLIP's two towers to OpenVINO IR, separately.

`XCLIPModel.forward()` is deliberately **not** exported. Its text embedding is
conditioned on the video it is being compared against::

    text_embeds = text_embeds + self.prompts_generator(text_embeds, img_features)

That is where X-CLIP's zero-shot accuracy comes from, and it is also why the
whole model cannot back a search index: an index needs a text vector that
exists before any particular video is in hand. So the two towers are exported
on their own, via `get_video_features` / `get_text_features`, which skip the
prompt generator and give a plain dual encoder. `verify.py` measures what that
costs.

The video tower takes a static `[1, 32, 3, 224, 224]`. 32 is not a batching
choice -- `vision_config.num_frames` is 32 and the temporal model is built for
it. The text tower keeps a dynamic batch, since scoring many queries at once is
ordinary.

The output is a standalone runtime package: both IR towers plus the source
checkpoint's configuration, tokenizer and preprocessing files. It does not
include the original PyTorch weights.
"""

import argparse
import os
from pathlib import Path
import shutil
from typing import Optional

import openvino as ov
import torch
from transformers import XCLIPModel


class VideoTower(torch.nn.Module):
    """`pixel_values -> video_embeds`, with no text in sight."""

    def __init__(self, model: XCLIPModel):
        super().__init__()
        self.model = model

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        # Transformers 4.57.6's get_video_features() calls self.mit() without
        # return_dict=True. Unlike the other towers, that module then returns a
        # tuple instead of BaseModelOutputWithPooling, so asking it for
        # pooler_output fails. Spell out the public method's few steps and make
        # the return contract explicit.
        batch_size, num_frames, num_channels, height, width = pixel_values.shape
        pixel_values = pixel_values.reshape(-1, num_channels, height, width)
        vision_outputs = self.model.vision_model(pixel_values=pixel_values)
        video_embeds = self.model.visual_projection(vision_outputs.pooler_output)
        cls_features = video_embeds.view(batch_size, num_frames, -1)
        mit_outputs = self.model.mit(cls_features, return_dict=True)
        return mit_outputs.pooler_output


class TextTower(torch.nn.Module):
    """`(input_ids, attention_mask) -> text_embeds`, with no video in sight."""

    def __init__(self, model: XCLIPModel):
        super().__init__()
        self.model = model

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> torch.Tensor:
        return self.model.get_text_features(
            input_ids=input_ids, attention_mask=attention_mask
        )


VIDEO_IR = "xclip_video.xml"
TEXT_IR = "xclip_text.xml"

#: IR weight precisions `convert` can write. `fp16` is weight compression on
#: save; the graph topology is identical either way.
PRECISIONS = ("fp32", "fp16")


def package_files(model_path: str) -> list[Path]:
    """Validate the local runtime assets before doing the expensive conversion."""
    root = Path(model_path)
    required = ("config.json", "tokenizer_config.json")
    missing = [name for name in required if not (root / name).is_file()]
    if not (root / "tokenizer.json").is_file() and not all(
        (root / name).is_file() for name in ("vocab.json", "merges.txt")
    ):
        missing.append("tokenizer.json (or vocab.json + merges.txt)")
    if missing:
        raise FileNotFoundError(
            f"Incomplete X-CLIP checkpoint at {model_path!r}; missing "
            f"{', '.join(missing)}. Prepare the complete local checkpoint before conversion."
        )
    return [
        root / name for name in (
            *required, "tokenizer.json", "vocab.json", "merges.txt",
            "special_tokens_map.json", "added_tokens.json",
            "preprocessor_config.json", "processor_config.json",
        ) if (root / name).is_file()
    ]


def convert(
    model_path: str,
    out_dir: Optional[str] = None,
    frames: int = 32,
    precision: str = "fp32",
) -> None:
    if precision not in PRECISIONS:
        raise ValueError(f"precision must be one of {PRECISIONS}, got {precision!r}")
    assets = package_files(model_path)
    if out_dir is None:
        out_dir = os.path.join(model_path, "openvino", precision)
    model = XCLIPModel.from_pretrained(
        model_path, torch_dtype=torch.float32, local_files_only=True
    )
    model.eval()
    configured = int(model.config.vision_config.num_frames)
    if configured != frames:
        raise ValueError(
            f"Checkpoint expects {configured} frames per clip, not {frames}; "
            "the temporal model is not resizable"
        )
    size = int(model.config.vision_config.image_size)
    context = int(model.config.text_config.max_position_embeddings)
    os.makedirs(out_dir, exist_ok=True)

    video_example = torch.randn(1, frames, 3, size, size)
    with torch.no_grad():
        video_ir = ov.convert_model(
            VideoTower(model),
            example_input=video_example,
            input=[("pixel_values", ov.PartialShape([1, frames, 3, size, size]))],
        )
    fp16 = precision == "fp16"
    ov.save_model(
        video_ir, os.path.join(out_dir, VIDEO_IR), compress_to_fp16=fp16
    )
    print(f"video tower -> {os.path.join(out_dir, VIDEO_IR)}")

    ids_example = torch.ones(2, context, dtype=torch.long)
    mask_example = torch.ones(2, context, dtype=torch.long)
    with torch.no_grad():
        text_ir = ov.convert_model(
            TextTower(model),
            example_input=(ids_example, mask_example),
            input=[
                ("input_ids", ov.PartialShape([-1, context])),
                ("attention_mask", ov.PartialShape([-1, context])),
            ],
        )
    ov.save_model(
        text_ir, os.path.join(out_dir, TEXT_IR), compress_to_fp16=fp16
    )
    print(f"text tower  -> {os.path.join(out_dir, TEXT_IR)}")
    for source in assets:
        target = Path(out_dir) / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
    print(f"runtime configuration/tokenizer -> {out_dir}")
    print(f"complete X-CLIP package -> {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="X-CLIP checkpoint directory")
    parser.add_argument(
        "--out",
        help="Output package directory (IR + config/tokenizer); defaults to <model>/openvino/<precision>",
    )
    parser.add_argument("--frames", type=int, default=32)
    parser.add_argument(
        "--precision",
        choices=PRECISIONS,
        default="fp32",
        help="IR weight precision (default: fp32); fp16 halves the IR size",
    )
    arguments = parser.parse_args()
    convert(arguments.model, arguments.out, arguments.frames, arguments.precision)


if __name__ == "__main__":
    main()
