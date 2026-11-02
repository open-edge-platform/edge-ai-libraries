# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Check the exported IR against PyTorch, and time it.

Synthetic inputs are enough and are used on purpose. The question here is
whether the conversion preserved the computation, which a fixed random tensor
answers exactly; decoding a real video would add a dependency and a download
without making the answer any sharper. `--video` runs a real clip through the
whole sampling path as well, for the separate question of whether the
preprocessing matches.
"""

import argparse
import os
import time

import numpy as np
import openvino as ov
import torch
from transformers import AutoTokenizer, XCLIPModel

from convert import TEXT_IR, VIDEO_IR

PROMPTS = [
    "a person cooking in a kitchen",
    "a dog running across a field",
    "someone falling down the stairs",
    "an empty room with no one in it",
]


def l2(array: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(array, axis=-1, keepdims=True)
    return array / np.clip(norm, 1e-12, None)


def compare(name: str, torch_out: np.ndarray, ov_out: np.ndarray) -> bool:
    """Agreement judged on scale-free terms, which is what survives to storage.

    An absolute tolerance would be meaningless here: these towers emit vectors
    with an L2 norm around 16, so the same relative error reads as a different
    absolute one per tower. Cosine is the criterion that matters most, since a
    vector is L2-normalized before it is ever written; relative error is kept
    beside it to catch a magnitude drift that cosine alone would hide.
    """
    max_abs = float(np.abs(torch_out - ov_out).max())
    relative = max_abs / float(np.abs(torch_out).max())
    cosines = (l2(torch_out) * l2(ov_out)).sum(axis=-1)
    worst_cos = float(cosines.min())
    ok = relative < 1e-3 and worst_cos > 0.9999
    print(
        f"  {name:<12} rel_err={relative:.3e}  min_cosine={worst_cos:.8f}  "
        f"(max_abs={max_abs:.3e})  {'PASS' if ok else 'FAIL'}"
    )
    return ok


def bench(callable_, repeats: int = 3) -> float:
    callable_()  # warm up: first OV call includes lazy compilation
    start = time.perf_counter()
    for _ in range(repeats):
        callable_()
    return (time.perf_counter() - start) / repeats * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--ir", required=True)
    parser.add_argument(
        "--device",
        default="AUTO:GPU,CPU",
        help="OpenVINO device or priority list, for example GPU or AUTO:GPU,CPU",
    )
    parser.add_argument("--video", help="Optional real clip, for the sampling path")
    arguments = parser.parse_args()

    model = XCLIPModel.from_pretrained(arguments.model, torch_dtype=torch.float32)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(arguments.model)
    frames = int(model.config.vision_config.num_frames)
    size = int(model.config.vision_config.image_size)
    context = int(model.config.text_config.max_position_embeddings)

    core = ov.Core()
    video_net = core.compile_model(os.path.join(arguments.ir, VIDEO_IR), arguments.device)
    text_net = core.compile_model(os.path.join(arguments.ir, TEXT_IR), arguments.device)

    print(f"model={arguments.model}")
    print(f"frames={frames} image_size={size} context={context} device={arguments.device}")
    passed = True

    # --- video tower ----------------------------------------------------------
    generator = torch.Generator().manual_seed(0)
    pixel_values = torch.randn(1, frames, 3, size, size, generator=generator)
    with torch.no_grad():
        torch_video = model.get_video_features(pixel_values=pixel_values).numpy()
    ov_video = video_net({"pixel_values": pixel_values.numpy()})[video_net.output(0)]
    print("video tower:")
    print(f"  output dim   {torch_video.shape[-1]}")
    passed &= compare("video", torch_video, ov_video)

    # --- text tower -----------------------------------------------------------
    tokens = tokenizer(
        PROMPTS, padding="max_length", max_length=context, truncation=True,
        return_tensors="pt",
    )
    with torch.no_grad():
        torch_text = model.get_text_features(
            input_ids=tokens["input_ids"], attention_mask=tokens["attention_mask"]
        ).numpy()
    ov_text = text_net(
        {
            "input_ids": tokens["input_ids"].numpy(),
            "attention_mask": tokens["attention_mask"].numpy(),
        }
    )[text_net.output(0)]
    print("text tower:")
    print(f"  output dim   {torch_text.shape[-1]}")
    passed &= compare("text", torch_text, ov_text)

    # --- shared space ---------------------------------------------------------
    # The dual-tower path is only usable if the two outputs are comparable at
    # all. A degenerate similarity matrix (every prompt equidistant) would pass
    # the per-tower checks above and still be useless.
    similarity = l2(ov_video) @ l2(ov_text).T
    print("dual-tower similarity (1 random clip x 4 prompts):")
    print(f"  {np.round(similarity[0], 4).tolist()}  spread={float(np.ptp(similarity)):.4f}")

    # --- latency --------------------------------------------------------------
    video_ms = bench(lambda: video_net({"pixel_values": pixel_values.numpy()}))
    text_ms = bench(
        lambda: text_net(
            {
                "input_ids": tokens["input_ids"].numpy(),
                "attention_mask": tokens["attention_mask"].numpy(),
            }
        )
    )
    with torch.no_grad():
        torch_video_ms = bench(lambda: model.get_video_features(pixel_values=pixel_values))
    print(f"latency ({arguments.device}):")
    print(f"  video OV     {video_ms:8.1f} ms/clip   (PyTorch {torch_video_ms:.1f} ms)")
    print(f"  text  OV     {text_ms:8.1f} ms/{len(PROMPTS)} prompts")
    for label, name in (("video", VIDEO_IR), ("text", TEXT_IR)):
        total = sum(
            os.path.getsize(os.path.join(arguments.ir, name.replace(".xml", suffix)))
            for suffix in (".xml", ".bin")
        )
        print(f"  {label} IR     {total / 1e6:8.1f} MB")

    # --- real clip, optional --------------------------------------------------
    if arguments.video:
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
        from core.multimodal.frames import sample_frames
        from core.multimodal.xclip_openvino import preprocess_frames

        sampled = sample_frames(arguments.video, frames)
        batch = preprocess_frames(sampled, size)
        real = video_net({"pixel_values": batch})[video_net.output(0)]
        print(f"real clip: {len(sampled)} frames sampled, vector norm "
              f"{float(np.linalg.norm(real)):.4f}")

    print("\nRESULT:", "PASS" if passed else "FAIL")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
