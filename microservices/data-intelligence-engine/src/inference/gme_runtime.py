# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenVINO Runtime implementation of Alibaba-NLP/gme-Qwen2-VL-2B-Instruct."""
from __future__ import annotations

import base64
import importlib
import json
import logging
import math
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import config
import numpy as np
import requests
from PIL import Image


class _Lazy:
    def __init__(self, module: str, attribute: str = ""):
        self._module, self._attribute, self._target = module, attribute, None

    def __getattr__(self, name):
        if self._target is None:
            target = importlib.import_module(self._module)
            self._target = getattr(target, self._attribute) if self._attribute else target
        return getattr(self._target, name)


ov = _Lazy("openvino")
props = _Lazy("openvino.properties")
hint = _Lazy("openvino.properties.hint")
AutoProcessor = _Lazy("transformers", "AutoProcessor")

if TYPE_CHECKING:
    from openvino import CompiledModel, InferRequest

DEFAULT_INSTRUCTION = "You are a helpful assistant."
IMAGE_FACTOR = 28
MIN_PIXELS = 4 * 28 * 28
MAX_PIXELS = 16384 * 28 * 28
MAX_RATIO = 200
DEFAULT_BATCH_SIZE = config.GME_BATCH_SIZE
# OpenVINO meta-devices: valid `device=` values not listed in Core.available_devices.
_META_DEVICE_PREFIXES = ("AUTO", "MULTI", "HETERO", "BATCH")
_IMAGE_LOAD_WORKERS = config.IMAGE_LOAD_WORKERS


def _as_list(value: str | Path | Image.Image | Sequence[str | Path | Image.Image] | None) -> list | None:
    if value is None:
        return None
    if isinstance(value, (str, Path, Image.Image)):
        return [value]
    values = list(value)
    # Flatten DataLoader-style batches of lists into individual samples.
    if values and all(isinstance(item, (list, tuple)) for item in values):
        return [item for batch in values for item in batch]
    return values


def _loader_batch_size(value: object) -> int | None:
    size = getattr(value, "batch_size", None)
    return size if isinstance(size, int) and size > 0 else None


class _Progress:
    """Progress bar (tqdm if available) shown only when work spans several chunks."""

    def __init__(self, total: int, enabled: bool, description: str = "encode") -> None:
        self.bar = None
        self.total = total if (enabled and total > 1) else 0
        self.done = 0
        self.description = description
        if not self.total:
            return
        try:
            from tqdm.autonotebook import tqdm
        except ImportError:
            return
        self.bar = tqdm(total=total, mininterval=1, miniters=10, desc=description)

    def update(self) -> None:
        if not self.total:
            return
        self.done += 1
        if self.bar is not None:
            self.bar.update(1)
        else:
            print(f"\r{self.description}: {self.done}/{self.total}", end="", file=sys.stderr, flush=True)

    def close(self) -> None:
        if not self.total:
            return
        if self.bar is not None:
            self.bar.close()
        else:
            print("", file=sys.stderr, flush=True)


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
        raise ValueError(f"image {width}x{height} is too extreme to resize: a side rounded to 0 pixels")
    if max(resized_height, resized_width) / min(resized_height, resized_width) > MAX_RATIO:
        # Clamp the long side; the result stays a multiple of IMAGE_FACTOR.
        logging.warning(
            "Absolute aspect ratio must be smaller than %s, got %s",
            MAX_RATIO, max(resized_height, resized_width) / min(resized_height, resized_width),
        )
        if resized_height > resized_width:
            resized_height = resized_width * MAX_RATIO
        else:
            resized_width = resized_height * MAX_RATIO
    return image.resize((resized_width, resized_height))


def load_image(value: str | Path | Image.Image) -> Image.Image:
    """Load an image from a PIL image, URL, file path or base64 data URI and resize it for GME."""
    if isinstance(value, Image.Image):
        image = value
    else:
        value = str(value)
        if value.startswith(("http://", "https://")):
            image = Image.open(
                requests.get(value, stream=True, timeout=config.IMAGE_HTTP_TIMEOUT).raw
            )
        elif value.startswith("file://"):
            image = Image.open(value[7:])
        elif value.startswith("data:image") and "base64," in value:
            image = Image.open(BytesIO(base64.b64decode(value.split("base64,", 1)[1])))
        else:
            image = Image.open(value)
    return _resize_for_gme(image.convert("RGB"))


def _load_images(values: list) -> list[Image.Image]:
    """Load/resize a batch of images in parallel, preserving input order."""
    if len(values) <= 1:
        return [load_image(value) for value in values]
    with ThreadPoolExecutor(max_workers=min(_IMAGE_LOAD_WORKERS, len(values))) as pool:
        return list(pool.map(load_image, values))


def package_ir_files(
    model_dir: str | Path, config: dict, precision: str | None = None
) -> tuple[str, str, str]:
    """Resolve ``(precision, language_xml, visual_xml)``, preferring the precision whose IRs are present."""
    precisions = config.get("precisions")
    if not precisions:
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


GME_DIMENSION = 1536
PACKAGE_CONFIG = "gme_openvino_config.json"


def find_package(model_path: str | Path) -> Path:
    """Return the package at ``model_path`` or the single package directly inside it."""
    root = Path(model_path)
    if (root / PACKAGE_CONFIG).is_file():
        return root
    nested = (
        [child for child in root.iterdir() if (child / PACKAGE_CONFIG).is_file()]
        if root.is_dir() else []
    )
    if len(nested) == 1:
        return nested[0]
    raise FileNotFoundError(
        f"No exported GME OpenVINO package at {str(model_path)!r} (looked for "
        f"{PACKAGE_CONFIG}). Put the package under ENGINE_MODEL_ROOT_PATH, "
        "and select its model ID with the source's embedding_model."
    )


def choose_precision(package: Path) -> str:
    """The package's precision, requiring complete XML/weights pairs."""
    metadata = json.loads((package / PACKAGE_CONFIG).read_text())
    precision, language, visual = package_ir_files(package, metadata)
    for name in (language, visual):
        path = package / name
        if not path.is_file() or not path.with_suffix(".bin").is_file():
            raise FileNotFoundError(
                f"GME precision {precision!r} is incomplete at {str(package)!r}: "
                f"expected {path.name} and {path.with_suffix('.bin').name}"
            )
    return precision


class _RequestPool:
    """Run independent infer requests in order; avoids ``ov.AsyncInferQueue``, which can return stale outputs."""

    def __init__(self, compiled: CompiledModel) -> None:
        self.compiled = compiled
        self.size = max(1, int(compiled.get_property("OPTIMAL_NUMBER_OF_INFER_REQUESTS")))
        self._requests: list[InferRequest] = []
        # Serializes `run`: concurrent callers would clobber the shared request slots.
        self._lock = threading.Lock()

    def _slots(self, count: int) -> list[InferRequest]:
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
                harvest(slot)
                for name, value in feed.items():
                    # Owned tensor copy: a shared view would alias the caller's array.
                    slots[slot].set_tensor(name, ov.Tensor(np.ascontiguousarray(value)))
                slots[slot].start_async()
                in_flight[slot] = job
            for slot in list(in_flight):
                harvest(slot)
        except BaseException:
            for slot in in_flight:
                slots[slot].wait()
            raise
        missing = [index for index, row in enumerate(results) if row is None]
        if missing:
            raise RuntimeError(f"inference produced no result for samples {missing}")
        return results  # type: ignore[return-value]


class GmeOpenVINO:
    """GME encoder running on OpenVINO Runtime; one image per input."""

    def __init__(
        self,
        model_dir: str | Path,
        device: str = "GPU.0",
        precision: str | None = None,
        fp32_math: bool | None = None,
        streams: int | str = 1,
        batch_mode: str = "auto",
        cache_dir: str | Path | None = None,
        min_image_tokens: int | None = None,
        max_image_tokens: int | None = None,
        max_length: int | None = None,
        dynamic_quantization_threshold: int | None = None,
        visual_dynamic_quantization_threshold: int | None = None,
    ) -> None:
        """streams: 1 favors latency, "auto" or N > 1 favors throughput; quantization thresholds are GPU-only."""
        self.model_dir = Path(model_dir)
        self._lock = threading.Lock()
        config_path = self.model_dir / "gme_openvino_config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"not an exported GME OpenVINO package: {self.model_dir}")
        self.config = __import__("json").loads(config_path.read_text())
        self.device = device

        self.precision, language_model, visual_model = package_ir_files(
            self.model_dir, self.config, precision
        )
        precision = self.precision

        processor_config = self.config["processor"]
        if min_image_tokens is None:
            min_image_tokens = processor_config["min_image_tokens"]
        if max_image_tokens is None:
            max_image_tokens = processor_config["max_image_tokens"]
        if min_image_tokens < 1 or max_image_tokens < 1 or min_image_tokens > max_image_tokens:
            raise ValueError(
                f"min_image_tokens={min_image_tokens} and max_image_tokens={max_image_tokens} "
                "must both be positive with min_image_tokens <= max_image_tokens"
            )
        self.max_image_tokens = max_image_tokens
        self.max_length = processor_config["max_length"] if max_length is None else max_length
        if self.max_length < 1:
            raise ValueError(f"max_length must be positive, got {self.max_length}")
        self.processor = AutoProcessor.from_pretrained(
            str(self.model_dir),
            local_files_only=True,
            min_pixels=min_image_tokens * IMAGE_FACTOR * IMAGE_FACTOR,
            max_pixels=max_image_tokens * IMAGE_FACTOR * IMAGE_FACTOR,
            use_fast=False,
        )
        padding_side = processor_config["padding_side"]
        if padding_side != "right":
            # Per-sample slicing assumes valid tokens come first.
            raise ValueError(f"package must be right-padded, got padding_side={padding_side!r}")
        self.processor.tokenizer.padding_side = padding_side
        self.embedding_dim = int(self.config["embedding_dim"])
        self.core = ov.Core()
        if cache_dir is not None:
            self.core.set_property({props.cache_dir(): str(cache_dir)})
        if not self._device_recognized(device):
            raise RuntimeError(
                f"OpenVINO device {device!r} unavailable; found {self.core.available_devices} "
                "(AUTO/MULTI/HETERO/BATCH meta-devices and a plain device with a '.N' suffix, "
                "e.g. 'GPU.0', are also accepted)"
            )
        if fp32_math is None:
            fp32_math = precision == "fp32"
        compile_config = {hint.inference_precision: ov.Type.f32} if fp32_math else {}
        compile_config.update(self._stream_config(streams))
        language_compile_config = dict(compile_config)
        visual_compile_config = dict(compile_config)
        # GPU_DYNAMIC_QUANTIZATION_THRESHOLD is rejected by non-GPU plugins.
        for name, value in (("dynamic_quantization_threshold", dynamic_quantization_threshold),
                            ("visual_dynamic_quantization_threshold",
                             visual_dynamic_quantization_threshold)):
            if value is None:
                continue
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            if not self._is_gpu_device(device):
                raise ValueError(
                    f"{name} is a GPU-plugin property and cannot be applied to device "
                    f"{device!r}; omit it for non-GPU devices"
                )
        if dynamic_quantization_threshold is not None:
            language_compile_config["GPU_DYNAMIC_QUANTIZATION_THRESHOLD"] = dynamic_quantization_threshold
        if visual_dynamic_quantization_threshold is not None:
            visual_compile_config["GPU_DYNAMIC_QUANTIZATION_THRESHOLD"] = visual_dynamic_quantization_threshold
        self.streams = streams
        if batch_mode not in ("auto", "per_sample", "padded"):
            raise ValueError(f"batch_mode must be auto/per_sample/padded, got {batch_mode!r}")
        # per_sample is faster on CPU, padded on GPU; decided by device name only.
        self.batch_mode = (
            ("per_sample" if device.upper().startswith("CPU") else "padded")
            if batch_mode == "auto"
            else batch_mode
        )
        self.language = self.core.compile_model(self.model_dir / language_model, device, language_compile_config)
        self.visual = self.core.compile_model(self.model_dir / visual_model, device, visual_compile_config)
        self.language_pool = _RequestPool(self.language)
        self.visual_pool = _RequestPool(self.visual)
        self._no_images = np.empty((0, self.embedding_dim), dtype=np.float32)

    def _device_recognized(self, device: str) -> bool:
        """True for an available device, a meta-device (AUTO, MULTI, ...) or an indexed device like ``GPU.0``."""
        device_name = device.split(":", 1)[0]
        if device_name in self.core.available_devices:
            return True
        if device_name in _META_DEVICE_PREFIXES:
            return True
        return "." not in device_name and any(
            available.startswith(f"{device_name}.") for available in self.core.available_devices
        )

    @staticmethod
    def _is_gpu_device(device: str) -> bool:
        """True only for a plain GPU device string, e.g. ``"GPU"`` or ``"GPU.1"`` (not meta-devices)."""
        return device.split(":", 1)[0].split(".", 1)[0].upper() == "GPU"

    @staticmethod
    def _stream_config(streams: int | str) -> dict:
        """LATENCY gives one request every core; THROUGHPUT overlaps requests."""
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
    def _instruction(instruction: str | None, is_query: bool) -> str:  # noqa: ARG004
        return instruction if instruction is not None else DEFAULT_INSTRUCTION

    def _language_embedding(
        self,
        inputs: dict[str, np.ndarray],
        image_embeds: list[np.ndarray] | None = None,
    ) -> np.ndarray:
        """``image_embeds`` holds each sample's visual tokens, or None for text-only."""
        input_ids = inputs["input_ids"]
        attention_mask = inputs["attention_mask"]
        if self.batch_mode == "padded":
            return self.language_pool.run([{
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "image_embeds": (
                    self._no_images if image_embeds is None
                    else np.concatenate(image_embeds, axis=0)
                ),
            }])[0]

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
        images: list[str | Image.Image],
        instruction: str,
    ) -> np.ndarray:
        if len(texts) != len(images) or not images:
            raise ValueError("image batch needs matching, non-empty texts and images")
        inputs = self.processor(
            text=[self._prompt(text, has_image=True, instruction=instruction) for text in texts],
            images=_load_images(images),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="np",
        )
        # Split the concatenated patches so each image is its own visual request.
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

    def embed(
        self,
        texts: Sequence[str | None] | None = None,
        images: Sequence[str | Path | Image.Image | None] | None = None,
        is_query: bool = True,
        instruction: str | None = None,
    ) -> np.ndarray:
        """Serialize the processor and inference across every adapter of this runtime."""
        with self._lock:
            return self._embed(texts, images, is_query, instruction)

    def _embed(
        self,
        texts: Sequence[str | None] | None = None,
        images: Sequence[str | Path | Image.Image | None] | None = None,
        is_query: bool = True,
        instruction: str | None = None,
    ) -> np.ndarray:
        """Encode one batch; ``images`` must be all images or all ``None`` (text-only)."""
        text_values = None if texts is None else list(texts)
        image_values = None if images is None else list(images)
        if image_values is not None and any(image is None for image in image_values):
            if not all(image is None for image in image_values):
                raise ValueError(
                    "an image batch must be either all images or all None; official GME "
                    "requires every example in a batch to be consistent"
                )
            image_values = None
        prompt = self._instruction(instruction, is_query)

        if image_values is None:
            if text_values is None:
                raise ValueError("provide texts, images, or both")
            if not all(isinstance(text, str) for text in text_values):
                raise ValueError("texts must be strings when no images are given")
            return self._encode_text_batch(text_values, prompt)
        if text_values is None:
            text_values = [None] * len(image_values)
        elif len(text_values) > len(image_values):
            text_values = text_values[: len(image_values)]
        elif len(text_values) < len(image_values):
            raise ValueError(
                f"got {len(text_values)} texts for {len(image_values)} images; "
                "fused input must be paired element-wise"
            )
        return self._encode_image_batch(text_values, image_values, prompt)

    def _encode(
        self,
        texts: list[str | None] | None,
        images: list | None,
        is_query: bool,
        instruction: str | None,
        batch_size: int | None,
        show_progress_bar: bool,
    ) -> np.ndarray:
        count = len(images) if images is not None else len(texts or [])
        if not count:
            raise ValueError("nothing to encode: texts and images are both empty")
        chunks = list(range(0, count, batch_size)) if batch_size else [0]
        progress = _Progress(len(chunks), show_progress_bar)
        try:
            embeddings = []
            for start in chunks:
                stop = count if batch_size is None else start + batch_size
                embeddings.append(
                    self.embed(
                        None if texts is None else texts[start:stop],
                        None if images is None else images[start:stop],
                        is_query=is_query,
                        instruction=instruction,
                    )
                )
                progress.update()
        finally:
            progress.close()
        return np.concatenate(embeddings, axis=0) if len(embeddings) > 1 else embeddings[0]

    def get_text_embeddings(
        self,
        texts: str | Sequence[str],
        instruction: str | None = None,
        is_query: bool = True,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
        show_progress_bar: bool = True,
    ) -> np.ndarray:
        values = _as_list(texts)
        if not values or not all(isinstance(text, str) for text in values):
            raise ValueError("texts must be a non-empty string or sequence of strings")
        return self._encode(values, None, is_query, instruction, batch_size, show_progress_bar)

    def get_image_embeddings(
        self,
        images: str | Image.Image | Sequence[str | Image.Image],
        instruction: str | None = None,
        is_query: bool = True,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
        show_progress_bar: bool = True,
    ) -> np.ndarray:
        batch_size = _loader_batch_size(images) or batch_size
        values = _as_list(images)
        if not values:
            raise ValueError("images must be a non-empty image or image sequence")
        return self._encode(None, values, is_query, instruction, batch_size, show_progress_bar)

    def get_fused_embeddings(
        self,
        texts: str | Sequence[str] | None = None,
        images: str | Image.Image | Sequence[str | Image.Image] | None = None,
        instruction: str | None = None,
        is_query: bool = True,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
        show_progress_bar: bool = True,
    ) -> np.ndarray:
        batch_size = _loader_batch_size(images) or batch_size
        text_values = _as_list(texts)
        image_values = _as_list(images)
        if text_values is None and image_values is None:
            raise ValueError("provide texts, images, or both")
        if text_values is not None and image_values is not None and len(text_values) != len(image_values):
            raise ValueError("texts and images must have the same length")
        return self._encode(text_values, image_values, is_query, instruction, batch_size, show_progress_bar)

    def encode(
        self,
        sentences: str | Sequence[str],
        *,
        prompt_name: str | None = None,
        instruction: str | None = None,
        is_query: bool = True,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
        show_progress_bar: bool = True,
    ) -> np.ndarray:
        """Sentence-transformers/MTEB-style text encoding; ``prompt_name`` is ignored."""
        del prompt_name
        return self.get_text_embeddings(
            sentences,
            instruction=instruction,
            is_query=is_query,
            batch_size=batch_size,
            show_progress_bar=show_progress_bar,
        )

    def encode_queries(
        self,
        queries: str | Sequence[str],
        *,
        instruction: str | None = None,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
        show_progress_bar: bool = True,
    ) -> np.ndarray:
        return self.get_text_embeddings(
            queries,
            instruction=instruction,
            is_query=True,
            batch_size=batch_size,
            show_progress_bar=show_progress_bar,
        )

    def encode_corpus(
        self,
        corpus: Sequence[dict[str, str]] | dict[str, Sequence[str]],
        *,
        batch_size: int | None = DEFAULT_BATCH_SIZE,
        show_progress_bar: bool = True,
    ) -> np.ndarray:
        """Encode sentence-transformers-style corpus rows with GME corpus prompts."""
        if isinstance(corpus, dict):
            texts = corpus.get("text")
            titles = corpus.get("title")
            if texts is None:
                raise ValueError("corpus dictionary must contain 'text'")
            if titles is not None and len(titles) != len(texts):
                raise ValueError("corpus 'title' and 'text' must have the same length")
            rows = [
                f"{titles[index]} {text}".strip() if titles is not None else text.strip()
                for index, text in enumerate(texts)
            ]
        else:
            rows = [f"{row.get('title', '')} {row['text']}".strip() for row in corpus]
        return self.get_text_embeddings(
            rows, is_query=False, batch_size=batch_size, show_progress_bar=show_progress_bar
        )