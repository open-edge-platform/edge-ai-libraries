# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenVINO Runtime implementation of Alibaba-NLP/gme-Qwen2-VL-2B-Instruct.

This module covers what ``GMEHandler`` needs: text, image and fused (image+text)
embeddings, on the query or the document side. Images must already be decoded
``PIL.Image`` objects; the service downloads and decodes media itself (with its
SSRF and path checks), so this module never touches the network or the
filesystem for an input.

It never imports the checkpoint's vendored ``gme_inference.py``. The exported
package contains the learned computation in two OpenVINO IRs. This module
deliberately retains Hugging Face's Qwen2-VL processor for tokenization and
pixel preprocessing, which is necessary to exactly preserve GME's special
tokens, dynamic image resizing, and image-token expansion.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

import numpy as np
import openvino as ov
from PIL import Image
from transformers import AutoProcessor

# GME's default system prompt, used for every document-side input.
DEFAULT_INSTRUCTION = "You are a helpful assistant."
# System prompt for a query when the caller gives none. GME is trained with a
# task instruction on the query side only, so queries and documents get
# different prompts (and embeddings) for the same text.
DEFAULT_QUERY_INSTRUCTION = "Find an image or text that matches the given query."
IMAGE_FACTOR = 28
MIN_PIXELS = 4 * 28 * 28
MAX_PIXELS = 16384 * 28 * 28
MAX_RATIO = 200
# Official GME's get_fused_embeddings() default. Chunking only bounds peak memory;
# it never changes a row, because rows are computed independently either way.
DEFAULT_BATCH_SIZE = 32
# OpenVINO virtual devices that select/combine real ones at compile time; never
# listed in Core.available_devices, but a valid `device=` value. See
# GmeOpenVINO._device_recognized.
_META_DEVICE_PREFIXES = ("AUTO", "MULTI", "HETERO", "BATCH")
# Mirrors official GME's DataLoader(num_workers=min(cpu_count//2, 8)) for image
# loading. With decoded images only the GME resize is left, which still benefits
# from overlapping a batch of large images.
_IMAGE_LOAD_WORKERS = max(1, min((os.cpu_count() or 1) // 2, 8))


def _round_by_factor(value: int, factor: int) -> int:
    return round(value / factor) * factor


def _resize_for_gme(image: Image.Image) -> Image.Image:
    width, height = image.size
    resized_height = max(IMAGE_FACTOR, _round_by_factor(height, IMAGE_FACTOR))
    resized_width = max(IMAGE_FACTOR, _round_by_factor(width, IMAGE_FACTOR))
    if resized_height * resized_width > MAX_PIXELS:
        scale = math.sqrt((height * width) / MAX_PIXELS)
        resized_height = math.floor(height / scale / IMAGE_FACTOR) * IMAGE_FACTOR
        resized_width = math.floor(width / scale / IMAGE_FACTOR) * IMAGE_FACTOR
    elif resized_height * resized_width < MIN_PIXELS:
        scale = math.sqrt(MIN_PIXELS / (height * width))
        resized_height = math.ceil(height * scale / IMAGE_FACTOR) * IMAGE_FACTOR
        resized_width = math.ceil(width * scale / IMAGE_FACTOR) * IMAGE_FACTOR
    if not resized_height or not resized_width:
        # Official divides by min(...) next and dies with ZeroDivisionError; say what
        # happened instead. Nothing upstream can encode is rejected here.
        raise ValueError(f"image {width}x{height} is too extreme to resize: a side rounded to 0 pixels")
    if max(resized_height, resized_width) / min(resized_height, resized_width) > MAX_RATIO:
        # Official warns and clamps the long side rather than failing, so an extreme
        # banner stays encodable; rejecting it here would drop an input GME accepts.
        # Clamping only shrinks, so the result is still a multiple of IMAGE_FACTOR.
        logging.warning(
            "Absolute aspect ratio must be smaller than %s, got %s",
            MAX_RATIO, max(resized_height, resized_width) / min(resized_height, resized_width),
        )
        if resized_height > resized_width:
            resized_height = resized_width * MAX_RATIO
        else:
            resized_width = resized_height * MAX_RATIO
    return image.resize((resized_width, resized_height))


def load_image(value: Image.Image) -> Image.Image:
    """Resize a decoded image exactly as the official GME inference helper."""
    if not isinstance(value, Image.Image):
        raise TypeError(f"GME images must be PIL.Image objects, got {type(value).__name__}")
    return _resize_for_gme(value.convert("RGB"))


def _load_images(values: list) -> list[Image.Image]:
    """Load/resize a batch of images, preserving input order.

    A single image skips the thread pool entirely -- there is nothing to overlap,
    and creating one would be pure overhead. ThreadPoolExecutor.map already
    returns results in submission order, so this needs no extra bookkeeping to
    keep images aligned with their paired texts.
    """
    if len(values) <= 1:
        return [load_image(value) for value in values]
    with ThreadPoolExecutor(max_workers=min(_IMAGE_LOAD_WORKERS, len(values))) as pool:
        return list(pool.map(load_image, values))


def package_ir_files(
    model_dir: str | Path, config: dict, precision: str | None = None
) -> tuple[str, str, str]:
    """``(precision, language_xml, visual_xml)`` a package directory resolves to.

    Without an explicit ``precision`` the package's precision is whichever one it
    actually ships: packages are often copied with a single precision's IRs while
    their config still lists all three, so the config's ``default_precision`` is
    only a tie-breaker when several are present. Packages that predate the
    ``precisions`` map are single-precision fp32.
    """
    precisions = config.get("precisions")
    if not precisions:  # backward compatibility with older single-precision packages
        return precision or "fp32", config["language_model"], config["visual_model"]
    if precision is None:
        model_dir = Path(model_dir)
        present = [
            name
            for name, files in precisions.items()
            if all(
                (model_dir / files[part]).is_file()
                and (model_dir / files[part]).with_suffix(".bin").is_file()
                for part in ("language", "visual")
            )
        ]
        default = config.get("default_precision")
        if default in present:
            precision = default
        elif len(present) == 1:
            precision = present[0]
        elif not present:
            raise FileNotFoundError(
                f"GME package {model_dir} has no complete language/visual IR pair "
                f"for any of {list(precisions)}"
            )
        else:
            raise ValueError(
                f"GME package {model_dir} ships {present} and its default_precision "
                f"{default!r} is not among them; keep a single precision's IRs"
            )
    if precision not in precisions:
        raise ValueError(f"precision {precision!r} not in {list(precisions)}")
    return precision, precisions[precision]["language"], precisions[precision]["visual"]


class _RequestPool:
    """Run independent inference requests over one compiled model, in order.

    A GME "batch" is N mutually independent samples, so it maps onto N infer
    requests rather than one padded N-row tensor. That keeps every sample at its
    own true sequence length (no padding compute, no dependence on what else
    shares the batch) and lets the plugin overlap samples across streams.

    Requests are created and driven explicitly rather than through
    ``ov.AsyncInferQueue``. The queue was measured to return a *stale* output for a
    later job -- a batch of two distinct images that happen to share a grid came
    back with row 0's embedding duplicated into row 1, silently and only sometimes
    (it depends on how the compiled model was used beforehand). Same-shaped feeds
    are exactly the common case (two 448x448 images, two equal-length queries), so
    each slot is driven with an explicit ``start_async`` + ``wait`` instead.
    """

    def __init__(self, compiled: ov.CompiledModel) -> None:
        self.compiled = compiled
        self.size = max(1, int(compiled.get_property("OPTIMAL_NUMBER_OF_INFER_REQUESTS")))
        self._requests: list[ov.InferRequest] = []
        # `run` mutates the shared request slots (set_tensor/start_async on
        # self._requests), so two threads calling it at once -- concurrent
        # requests offloaded to the threadpool -- would clobber each other's
        # in-flight tensors. Serialize a single pool's inference; the language
        # and visual pools are separate instances, so they still overlap.
        self._lock = threading.Lock()

    def _slots(self, count: int) -> list[ov.InferRequest]:
        """Reuse requests across calls; a request holds activations, so grow lazily."""
        while len(self._requests) < count:
            self._requests.append(self.compiled.create_infer_request())
        return self._requests[:count]

    def run(self, feeds: list[dict[str, np.ndarray]]) -> list[np.ndarray]:
        if not feeds:
            return []
        with self._lock:
            return self._run(feeds)

    def _run(self, feeds: list[dict[str, np.ndarray]]) -> list[np.ndarray]:
        slots = self._slots(min(self.size, len(feeds)))
        results: list[np.ndarray | None] = [None] * len(feeds)
        in_flight: dict[int, int] = {}  # slot -> job currently occupying it

        def harvest(slot: int) -> None:
            job = in_flight.pop(slot, None)
            if job is None:
                return
            slots[slot].wait()
            # The request's output buffer is reused by the next job: copy now.
            results[job] = slots[slot].get_output_tensor(0).data.astype(np.float32, copy=True)

        try:
            for job, feed in enumerate(feeds):
                slot = job % len(slots)
                harvest(slot)  # free the slot before overwriting its inputs
                for name, value in feed.items():
                    # Copy into an owned tensor: the request outlives this loop
                    # iteration, and a shared view would alias the caller's array.
                    slots[slot].set_tensor(name, ov.Tensor(np.ascontiguousarray(value)))
                slots[slot].start_async()
                in_flight[slot] = job
            for slot in list(in_flight):
                harvest(slot)
        except BaseException:
            # In-flight requests still reference tensors we are about to drop.
            for slot in in_flight:
                slots[slot].wait()
            raise
        missing = [index for index, row in enumerate(results) if row is None]
        if missing:
            raise RuntimeError(f"inference produced no result for samples {missing}")
        return results  # type: ignore[return-value]


class GmeOpenVINO:
    """GME encoder backed entirely by OpenVINO Runtime neural computation.

    One image per input is supported, matching the official model limitation.
    ``get_text_embeddings`` / ``get_image_embeddings`` / ``get_fused_embeddings``
    follow official ``GmeQwen2VL``: they chunk by ``batch_size`` and select the
    prompt with ``is_query`` and ``instruction``.

    The request pools are locked, but the Hugging Face processor in front of
    them is not known to be reentrant: callers sharing one instance across
    threads should serialize calls, as ``GMEHandler`` does.

    Batching works for any number of samples with no per-batch-size export:

    * The visual IR is invoked once per image. Qwen2-VL's vision tower has no
      batch dimension at all -- images become one concatenated patch sequence whose
      attention is block-diagonal per image, and each image's rotary table lookup
      depends only on its own grid -- so per-image invocation computes the same
      function as feeding several ``image_grid_thw`` rows at once, and is cheaper:
      a shared sequence costs O((sum L)^2) masked attention instead of O(sum L^2).
    * The language IR is invoked once per sample at its true length on CPU, which
      makes a batch bit-identical to the same items encoded one by one and lets
      streams overlap samples. On other devices it gets one padded [B, S] call the
      way the official model does, because per-request submission overhead
      dominates short sequences on a GPU.
    """

    def __init__(
        self,
        model_dir: str | Path,
        device: str = "GPU.0",
        precision: str | None = None,
        streams: int | str = 1,
        cache_dir: str | Path | None = None,
    ) -> None:
        """precision: one of the keys in the package config's ``precisions`` map
        (``fp32``/``int8``/``int4``); defaults to the package ``default_precision``.
        fp32 weights run with an f32 inference-precision hint so the reference is
        reproduced exactly; quantized models use the device default for speed.
        streams: execution streams per IR. ``1`` (default) gives one stream all
        cores, the lowest latency for one sample; ``"auto"`` lets the plugin pick,
        or pass an int to pin it. More streams raise multi-sample throughput at
        some single-sample latency and memory; output is unaffected.
        cache_dir: enables OpenVINO's compiled-model cache so a later process with
        the same package/device/precision/streams skips recompilation. ``None``
        (default) disables it."""
        self.model_dir = Path(model_dir)
        config_path = self.model_dir / "gme_openvino_config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"not an exported GME OpenVINO package: {self.model_dir}")
        self.config = json.loads(config_path.read_text())
        self.device = device

        self.precision, language_model, visual_model = package_ir_files(
            self.model_dir, self.config, precision
        )

        processor_config = self.config["processor"]
        self.max_length = processor_config["max_length"]
        self.processor = AutoProcessor.from_pretrained(
            str(self.model_dir),
            min_pixels=processor_config["min_image_tokens"] * IMAGE_FACTOR * IMAGE_FACTOR,
            max_pixels=processor_config["max_image_tokens"] * IMAGE_FACTOR * IMAGE_FACTOR,
            use_fast=False,
        )
        padding_side = processor_config["padding_side"]
        if padding_side != "right":
            # Per-sample slicing below assumes valid tokens come first.
            raise ValueError(f"package must be right-padded, got padding_side={padding_side!r}")
        self.processor.tokenizer.padding_side = padding_side
        self.embedding_dim = int(self.config["embedding_dim"])
        self.core = ov.Core()
        if cache_dir is not None:
            self.core.set_property({ov.properties.cache_dir(): str(cache_dir)})
        if not self._device_recognized(device):
            raise RuntimeError(
                f"OpenVINO device {device!r} unavailable; found {self.core.available_devices} "
                "(AUTO/MULTI/HETERO/BATCH meta-devices and a plain device with a '.N' suffix, "
                "e.g. 'GPU.0', are also accepted)"
            )
        compile_config = (
            {ov.properties.hint.inference_precision: ov.Type.f32} if self.precision == "fp32" else {}
        )
        compile_config.update(self._stream_config(streams))
        self.streams = streams
        # Name-based: only a device string starting with "CPU" runs per sample;
        # anything else, including meta-devices, gets the padded call.
        self.batch_mode = "per_sample" if device.upper().startswith("CPU") else "padded"
        self.language = self.core.compile_model(self.model_dir / language_model, device, compile_config)
        self.visual = self.core.compile_model(self.model_dir / visual_model, device, compile_config)
        self.language_pool = _RequestPool(self.language)
        self.visual_pool = _RequestPool(self.visual)
        self._no_images = np.empty((0, self.embedding_dim), dtype=np.float32)

    def _device_recognized(self, device: str) -> bool:
        """True if `device` is a real device or a device OpenVINO otherwise accepts.

        `core.available_devices` only lists concrete plugins with detected hardware
        (e.g. ``["CPU", "GPU"]``), so a strict membership check rejects every legal
        multi-device string: ``"AUTO"``, ``"AUTO:CPU"``, ``"MULTI:CPU,GPU"``,
        ``"HETERO:GPU,CPU"``, ``"BATCH:GPU(4)"``, and a device index like
        ``"GPU.0"``. Rather than reimplement OpenVINO's device-string grammar, this
        only recognizes the plain-device and known-meta-device-prefix cases and
        otherwise defers to `compile_model`'s own error -- good enough to catch the
        common typo (e.g. `"gpu"` lowercase) without blocking a legitimate config.

        Indices go both ways: a lone GPU is listed as ``"GPU"`` yet ``"GPU.0"``
        compiles, and several GPUs are listed as ``"GPU.0"``/``"GPU.1"`` yet a plain
        ``"GPU"`` compiles.
        """
        available = self.core.available_devices
        device_name = device.split(":", 1)[0]
        if device_name in available or device_name in _META_DEVICE_PREFIXES:
            return True
        base = device_name.split(".", 1)[0]
        if base != device_name:
            return base in available
        return any(name.startswith(f"{device_name}.") for name in available)

    @staticmethod
    def _stream_config(streams: int | str) -> dict:
        """LATENCY gives one request every core; THROUGHPUT overlaps requests."""
        hint = ov.properties.hint
        if streams == "auto":
            return {hint.performance_mode: hint.PerformanceMode.THROUGHPUT}
        if not isinstance(streams, int) or streams < 1:
            raise ValueError(f"streams must be a positive int or 'auto', got {streams!r}")
        if streams == 1:
            return {hint.performance_mode: hint.PerformanceMode.LATENCY}
        return {
            hint.performance_mode: hint.PerformanceMode.THROUGHPUT,
            ov.properties.num_streams: streams,
        }

    @staticmethod
    def _prompt(text: str | None, has_image: bool, instruction: str) -> str:
        content = "<|vision_start|><|image_pad|><|vision_end|>" if has_image else ""
        if text is not None:
            content += text
        return (
            f"<|im_start|>system\n{instruction}<|im_end|>\n"
            f"<|im_start|>user\n{content}<|im_end|>\n"
            f"<|im_start|>assistant\n<|endoftext|>"
        )

    @staticmethod
    def _instruction(instruction: str | None, is_query: bool) -> str:
        """The system instruction for a prompt, selected by ``is_query``.

        As in official GME, a query uses ``instruction`` (``DEFAULT_QUERY_INSTRUCTION``
        when it is None) and a document always uses ``DEFAULT_INSTRUCTION``.
        """
        if not is_query:
            return DEFAULT_INSTRUCTION
        return instruction if instruction is not None else DEFAULT_QUERY_INSTRUCTION

    def _language_embedding(
        self,
        inputs: dict[str, np.ndarray],
        image_embeds: list[np.ndarray] | None = None,
    ) -> np.ndarray:
        """Decode the batch, per ``batch_mode``.

        ``image_embeds`` holds each sample's visual tokens, or None for text-only.
        """
        input_ids = inputs["input_ids"]
        attention_mask = inputs["attention_mask"]
        if self.batch_mode == "padded":
            # One [B, S] call, exactly the official layout: every sample's visual
            # tokens are concatenated and masked_scatter distributes them across the
            # flattened batch, one image-pad slot per row.
            return self.language_pool.run([{
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "image_embeds": (
                    self._no_images if image_embeds is None
                    else np.concatenate(image_embeds, axis=0)
                ),
            }])[0]

        # Per-sample: trimming the right padding makes the result independent of the
        # batch it was encoded in, and skips the decoder work the padding would cost.
        lengths = attention_mask.sum(axis=1).astype(np.int64)
        feeds = [
            {
                "input_ids": input_ids[row : row + 1, : lengths[row]],
                "attention_mask": attention_mask[row : row + 1, : lengths[row]],
                "image_embeds": self._no_images if image_embeds is None else image_embeds[row],
            }
            for row in range(input_ids.shape[0])
        ]
        return np.concatenate(self.language_pool.run(feeds), axis=0)

    def _encode_text_batch(self, texts: list[str], instruction: str) -> np.ndarray:
        prompts = [self._prompt(text, has_image=False, instruction=instruction) for text in texts]
        inputs = self.processor(
            text=prompts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="np",
        )
        return self._language_embedding(inputs)

    def _encode_image_batch(
        self,
        texts: list[str | None],
        images: list[Image.Image],
        instruction: str,
    ) -> np.ndarray:
        inputs = self.processor(
            text=[self._prompt(text, has_image=True, instruction=instruction) for text in texts],
            images=_load_images(images),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="np",
        )
        # The processor concatenates every image's patches into one array; split it
        # back so each image becomes its own visual request. Block-diagonal vision
        # attention makes this bit-identical to one multi-row call, and faster.
        grid_thw = inputs["image_grid_thw"]
        bounds = np.concatenate([[0], np.cumsum(np.prod(grid_thw, axis=1, dtype=np.int64))])
        visual_feeds = [
            {
                "pixel_values": inputs["pixel_values"][bounds[index] : bounds[index + 1]],
                "image_grid_thw": grid_thw[index : index + 1],
            }
            for index in range(grid_thw.shape[0])
        ]
        return self._language_embedding(inputs, self.visual_pool.run(visual_feeds))

    def _encode(
        self,
        texts: list[str] | None,
        images: list[Image.Image] | None,
        is_query: bool,
        instruction: str | None,
        batch_size: int | None,
    ) -> np.ndarray:
        """Chunk into ``batch_size`` groups and concatenate, like official GME.

        Chunking is a memory knob only. Each row is computed from its own sample, so
        the concatenation of the chunks is the same array a single-chunk call returns.
        """
        count = len(images) if images is not None else len(texts)
        prompt = self._instruction(instruction, is_query)
        step = batch_size or count
        embeddings = []
        for start in range(0, count, step):
            stop = start + step
            if images is None:
                embeddings.append(self._encode_text_batch(texts[start:stop], prompt))
            else:
                chunk_images = images[start:stop]
                chunk_texts = [None] * len(chunk_images) if texts is None else texts[start:stop]
                embeddings.append(self._encode_image_batch(chunk_texts, chunk_images, prompt))
        return np.concatenate(embeddings, axis=0) if len(embeddings) > 1 else embeddings[0]

    def get_text_embeddings(
        self,
        texts: Sequence[str],
        instruction: str | None = None,
        is_query: bool = True,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
    ) -> np.ndarray:
        values = list(texts)
        if not values or not all(isinstance(text, str) for text in values):
            raise ValueError("texts must be a non-empty sequence of strings")
        return self._encode(values, None, is_query, instruction, batch_size)

    def get_image_embeddings(
        self,
        images: Sequence[Image.Image],
        instruction: str | None = None,
        is_query: bool = True,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
    ) -> np.ndarray:
        values = list(images)
        if not values:
            raise ValueError("images must be a non-empty sequence of images")
        return self._encode(None, values, is_query, instruction, batch_size)

    def get_fused_embeddings(
        self,
        texts: Sequence[str],
        images: Sequence[Image.Image],
        instruction: str | None = None,
        is_query: bool = True,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
    ) -> np.ndarray:
        text_values = list(texts)
        image_values = list(images)
        if not image_values or len(text_values) != len(image_values):
            raise ValueError("texts and images must be non-empty and the same length")
        return self._encode(text_values, image_values, is_query, instruction, batch_size)
