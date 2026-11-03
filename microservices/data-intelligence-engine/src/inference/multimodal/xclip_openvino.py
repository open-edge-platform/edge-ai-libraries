# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""X-CLIP as a dual encoder, on OpenVINO.

One clip in, one vector out -- not one per frame. A short video is a thing, and
a projection that wrote a vector per frame would make the record count depend
on the video's length, which is exactly what "do not chunk a short video" rules
out.

**This is the dual-tower path, and that is a deliberate, costly choice.**
X-CLIP's published zero-shot numbers come from `XCLIPModel.forward()`, which
conditions the text embedding on the video being scored::

    text_embeds = text_embeds + self.prompts_generator(text_embeds, img_features)

An index cannot use that: it needs a text vector that exists before any
particular video is in hand. So `get_video_features` / `get_text_features` are
used instead, the prompt generator is skipped, and some accuracy goes with it.
`scripts/eval_retrieval` measures how much, rather than leaving it to be
guessed at. Anyone comparing this against the paper should compare against the
dual-tower number, not the headline one.

The IR is built by `scripts/xclip/convert.py` into `openvino/<precision>/`
next to the checkpoint. Bare `openvino/` and package-root exports are supported
as well. All conversion happens before engine startup.
"""

import json
import os
import threading
from typing import Any, List, Optional, Sequence

from core.content import ROLE_L1_SEGMENT, ROLE_SHORT_VIDEO
from core.multimodal.embeddings import Vector, normalize

VIDEO_IR = "xclip_video.xml"
TEXT_IR = "xclip_text.xml"

def _contains_ir(directory: str) -> bool:
    return all(
        os.path.isfile(os.path.join(directory, name))
        and os.path.isfile(os.path.join(directory, os.path.splitext(name)[0] + ".bin"))
        for name in (VIDEO_IR, TEXT_IR)
    )


def find_ir_dir(model_path: str) -> Optional[str]:
    """Where a checkpoint's IR lives, or None if it was never converted.

    Each precision's IR sits in `openvino/<precision>/`; a bare `openvino/`
    holds older fp32 exports. The prepared package determines its weights:
    fp32 is preferred, then bare openvino/, then fp16, then the package root.
    Use a separate model ID and package directory to choose different weights.
    """
    for name in ("fp32", "", "fp16"):
        directory = os.path.join(model_path, "openvino", name) if name else os.path.join(
            model_path, "openvino"
        )
        if _contains_ir(directory):
            return directory
    if _contains_ir(model_path):
        return model_path
    return None

#: ImageNet normalization, the default in every microsoft/xclip checkpoint's
#: `preprocessor_config.json`. The checkpoint's own values win when they
#: differ (see `XClipOpenVinoEmbedding`); these are the fallback.
IMAGE_MEAN = (0.485, 0.456, 0.406)
IMAGE_STD = (0.229, 0.224, 0.225)


def preprocess_frames(
    frames: Sequence[Any],
    size: int = 224,
    mean: Sequence[float] = IMAGE_MEAN,
    std: Sequence[float] = IMAGE_STD,
) -> Any:
    """Sampled frames as the `[1, frames, 3, size, size]` the video tower wants.

    Shorter edge resized to `size`, then centre-cropped to a square -- the
    preprocessing every microsoft/xclip checkpoint was trained with, stated in
    its `preprocessor_config.json` (`do_resize` + `do_center_crop`, ImageNet
    normalization, bilinear resampling). Anything else -- a square resize,
    CLIP's normalization -- measurably compresses the similarity margins; see
    `scripts/xclip/CHECKPOINTS.md` §4.
    """
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    mean = np.array(mean, dtype=np.float32).reshape(3, 1, 1)
    std = np.array(std, dtype=np.float32).reshape(3, 1, 1)
    planes = []
    for frame in frames:
        if not isinstance(frame, Image.Image):
            frame = Image.fromarray(np.asarray(frame))
        frame = frame.convert("RGB")
        width, height = frame.size
        short, long = (width, height) if width <= height else (height, width)
        # `int`, not `round`: matches transformers' get_resize_output_image_size
        scaled_long = int(size * long / short)
        new_size = (size, scaled_long) if width <= height else (scaled_long, size)
        frame = frame.resize(new_size, Image.BILINEAR)
        width, height = frame.size
        left = (width - size) // 2
        top = (height - size) // 2
        frame = frame.crop((left, top, left + size, top + size))
        array = np.asarray(frame, dtype=np.float32).transpose(2, 0, 1) / 255.0
        planes.append((array - mean) / std)
    return np.stack(planes)[None, ...].astype(np.float32)


class XClipOpenVinoEmbedding:
    """X-CLIP's video and text towers, compiled and held."""

    # A clip of up to a minute, and nothing else: no still-image encoder, and
    # the temporal model is built for exactly `frames_per_clip` frames of one
    # continuous shot, not for the many shots of a long recording.
    # An L1 segment is a short clip cut from a long video, so it is in reach too.
    supported_roles = frozenset({ROLE_SHORT_VIDEO, ROLE_L1_SEGMENT})

    def __init__(
        self,
        model_path: str,
        device: str = "CPU",
        frames_per_clip: int = 32,
        ir_dir: Optional[str] = None,
    ):
        import openvino as ov  # noqa: PLC0415

        self.model_path = model_path
        self.device = device
        self.frames_per_clip = frames_per_clip
        if ir_dir is not None:
            if not _contains_ir(ir_dir):
                raise FileNotFoundError(
                    f"No X-CLIP IR in {ir_dir!r}; prepare the model first"
                )
            self.ir_dir = ir_dir
        else:
            self.ir_dir = find_ir_dir(model_path)
            if self.ir_dir is None:
                # Download and export outside the engine; loading only loads.
                raise FileNotFoundError(
                    f"No X-CLIP IR under {model_path!r}; prepare the "
                    "model first (scripts/xclip/convert.py)"
                )
        core = ov.Core()
        self._video = core.compile_model(os.path.join(self.ir_dir, VIDEO_IR), device)
        self._text = core.compile_model(os.path.join(self.ir_dir, TEXT_IR), device)
        # Declared, not probed: running a model to learn a constant the config
        # already states would cost a full inference per source construction.
        self.dimension = int(self._video.output(0).get_partial_shape()[-1].get_length())
        self.image_size = int(self._video.input(0).get_partial_shape()[-1].get_length())
        exported = int(self._video.input(0).get_partial_shape()[1].get_length())
        if exported != frames_per_clip:
            raise ValueError(
                f"frames_per_clip={frames_per_clip} does not match the IR in "
                f"{self.ir_dir!r}, exported for {exported} frames"
            )
        self.context_length = int(
            self._text.input(0).get_partial_shape()[-1].get_length()
        )
        self.image_mean, self.image_std = self._normalization()
        self._tokenizer = None
        self._tokenizer_lock = threading.Lock()

    # --- model files ----------------------------------------------------------

    def _normalization(self) -> tuple:
        """Normalization the checkpoint's `preprocessor_config.json` states.

        Read from the checkpoint rather than assumed: the microsoft checkpoints
        all happen to use ImageNet normalization today, and the fallback is for
        a checkpoint that does not say.
        """
        try:
            with open(
                os.path.join(self.model_path, "preprocessor_config.json"),
                encoding="utf-8",
            ) as file:
                config = json.load(file)
            return tuple(config["image_mean"]), tuple(config["image_std"])
        except (OSError, ValueError, KeyError):
            return IMAGE_MEAN, IMAGE_STD

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            with self._tokenizer_lock:
                if self._tokenizer is None:
                    from transformers import AutoTokenizer  # noqa: PLC0415

                    self._tokenizer = AutoTokenizer.from_pretrained(
                        self.model_path, local_files_only=True
                    )
        return self._tokenizer

    # --- MultimodalEmbedding --------------------------------------------------

    def embed_text(self, texts: Sequence[str]) -> List[Vector]:
        texts = list(texts)
        if not texts:
            return []
        tokens = self.tokenizer(
            texts,
            padding="max_length",
            max_length=self.context_length,
            truncation=True,
            return_tensors="np",
        )
        output = self._text(
            {
                "input_ids": tokens["input_ids"],
                "attention_mask": tokens["attention_mask"],
            }
        )[self._text.output(0)]
        return [normalize(row) for row in output]

    def embed_image(self, images: Sequence[Any]) -> List[Vector]:
        # X-CLIP has no still-image encoder: the vision tower is wrapped in a
        # temporal model that expects a sequence. Feeding it one frame repeated
        # 32 times would return a vector, and that vector would describe "a
        # video in which nothing moves" -- plausible, and wrong for a photo.
        # Images go to an image model (GME); reaching here means
        # block-kind routing sent the wrong block.
        raise NotImplementedError(
            "X-CLIP embeds clips, not stills; route image blocks to an image source"
        )

    def embed_video(self, frames: Sequence[Any]) -> Vector:
        from core.multimodal.frames import pad_to  # noqa: PLC0415

        batch = preprocess_frames(
            pad_to(frames, self.frames_per_clip),
            self.image_size,
            self.image_mean,
            self.image_std,
        )
        output = self._video({"pixel_values": batch})[self._video.output(0)]
        return normalize(output[0])


__all__ = [
    "IMAGE_MEAN",
    "IMAGE_STD",
    "TEXT_IR",
    "VIDEO_IR",
    "XClipOpenVinoEmbedding",
    "find_ir_dir",
    "preprocess_frames",
]
