# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenVINO Runtime implementation of Alibaba-NLP/gme-Qwen2-VL-2B-Instruct.

Ported from the GME OpenVINO export project (``src/gme_openvino.py``) by way of
the Data Intelligence Engine copy (``engine/src/core/gme_runtime.py``), keeping
the engine's fixes: the per-pool inference lock, indexed-device recognition and
an explicit instruction honoured on the document side. Service-specific changes:

* Images must already be decoded ``PIL.Image`` objects. The upstream helper also
  fetches URLs, opens local paths and decodes data URIs; here the service
  downloads and decodes media itself (with its SSRF and path checks), so this
  module never touches the network or the filesystem for an input.
* Batch size and image-resize workers are constants instead of engine settings.
* OpenVINO properties are looked up on ``ov`` when used rather than imported
  at module level, so importing this module needs only the top-level package.
* A device such as ``GPU.0`` is accepted when OpenVINO lists the plain ``GPU``
  (upstream behaviour) as well as the reverse (engine behaviour).

It never imports the checkpoint's vendored ``gme_inference.py``. The exported
package contains the learned computation in two OpenVINO IRs. This module
deliberately retains Hugging Face's Qwen2-VL processor for tokenization and
pixel preprocessing, which is necessary to exactly preserve GME's special
tokens, dynamic image resizing, and image-token expansion.
"""
from __future__ import annotations

import logging
import math
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

import numpy as np
import openvino as ov
from PIL import Image
from transformers import AutoProcessor

DEFAULT_INSTRUCTION = "You are a helpful assistant."
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


def _as_list(value: Image.Image | Sequence[Image.Image] | str | Sequence[str] | None) -> list | None:
    if value is None:
        return None
    if isinstance(value, (str, Image.Image)):
        return [value]
    values = list(value)
    # Official GME accepts a DataLoader for images. Its batches are normally
    # lists (the official collate function is identity), so flatten those while
    # keeping every actual image object/path as one sample.
    if values and all(isinstance(item, (list, tuple)) for item in values):
        return [item for batch in values for item in batch]
    return values


def _loader_batch_size(value: object) -> int | None:
    """Official GME takes its batch size from a DataLoader when given one."""
    size = getattr(value, "batch_size", None)
    return size if isinstance(size, int) and size > 0 else None


class _Progress:
    """Official GME wraps its encode loop in tqdm; mirror that without requiring it.

    One deliberate difference from upstream: a bar is only drawn when the work is
    actually split into several chunks. A one-chunk bar carries no information and
    upstream only prints it because its loop is unconditional.
    """

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
            return  # plain stderr counter below
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
        # Upstream would fetch a URL or open a path here; callers of this service
        # runtime decode media first so that their own URL/path checks apply.
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
    this had to go. Explicit ``start_async`` + ``wait`` per slot is what the C++
    runtime already does, and 07_validate_batch.py now pins both against distinct
    same-shape samples.
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

    The public API mirrors official ``GmeQwen2VL``: ``embed`` is the single-batch
    primitive, ``get_text_embeddings`` / ``get_image_embeddings`` /
    ``get_fused_embeddings`` chunk by ``batch_size`` (default 32, as upstream) with
    an optional progress bar, and ``encode`` / ``encode_queries`` / ``encode_corpus``
    are the sentence-transformers-style aliases.

    **Not thread-safe.** One instance holds one ``_RequestPool`` per IR, and a pool
    lends out and reuses its ``ov.InferRequest`` objects across calls (see
    ``_RequestPool``); calling any ``encode_*``/``get_*`` method on the *same*
    instance from two threads at once races on that shared pool state. This
    matters because the README's deployment notes also recommend reusing one
    instance across requests to avoid recompiling the IRs -- that advice is about
    process lifetime, not concurrency: reuse one instance sequentially, or across
    threads only behind a lock, or give each worker thread/process its own
    instance (they can still share a ``cache_dir`` so only the first one actually
    compiles).

    Batching works for any number of samples with no per-batch-size export:

    * The visual IR is invoked once per image. Qwen2-VL's vision tower has no
      batch dimension at all -- images become one concatenated patch sequence whose
      attention is block-diagonal per image, and each image's rotary table lookup
      depends only on its own grid -- so per-image invocation computes the same
      function as feeding several ``image_grid_thw`` rows at once. Measured
      bit-identical against a deliberately B=2-traced IR (max abs diff 0.0), and
      cheaper: a shared sequence costs O((sum L)^2) masked attention instead of
      O(sum L^2). Tracing also bakes the image count in (``rot_pos_emb`` loops over
      the grid rows in Python), so a traced IR rejects a row count it was not
      traced with -- per-image invocation is what makes any N work from one export.
    * The language IR is driven by ``batch_mode``. ``"per_sample"`` invokes it once
      per sample at that sample's true length, which makes a batch bit-identical to
      the same items encoded one by one; ``"padded"`` sends one [B, S] call the way
      the official model does, where rows shift slightly with batch composition.

    Which one is faster is a property of the device, so ``batch_mode="auto"``
    (the default) picks per measurement:

    * CPU: one request already saturates every core, so a padded N-row call is no
      faster than N sequential calls (measured 1.00x at N=4 and N=8). Per-sample
      wins because it drops the padding work and, with ``streams``, overlaps
      samples for ~1.9x.
    * GPU: per-request submission overhead dominates short sequences, so folding
      the batch into one call is 2.4x faster per embedding (22 ms vs 53 ms at
      N=4) and extra streams do not recover it. Padded wins.
    """

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
        """precision: one of the keys in the package config's ``precisions`` map
        (``fp32``/``int8``/``int4``); defaults to the package ``default_precision``.
        fp32_math: force f32 inference-precision hint (defaults to True only for the
        fp32 weights, so the reference is reproduced exactly; quantized models use the
        device default for best speed).
        streams: execution streams per IR, trading single-sample latency for batch
        throughput. ``1`` (default) gives one stream all cores -- lowest latency for
        one sample. ``"auto"`` lets the plugin pick (4 on a 16-core CPU), or pass an
        int to pin it; multi-sample calls then run ~1.9x faster while a lone sample
        is ~1.3x slower and each extra stream costs ~0.2 GB. Output is unaffected.
        batch_mode: how the language IR consumes a batch -- ``"per_sample"`` (one
        request per sample, bit-identical to sequential), ``"padded"`` (one [B, S]
        request, like the official model), or ``"auto"`` (default: per_sample on
        CPU, padded on GPU, matching where each is faster).
        cache_dir: enables OpenVINO's compiled-model cache (``ov.properties.cache_dir``)
        so a second process with the same package/device/precision/streams loads a
        cached blob instead of recompiling. ``None`` (default) disables it, matching
        prior behavior. Recommended for GPU, where compiling the INT8 language IR from
        scratch is tens of seconds; every short-lived CLI/benchmark process in this
        project pays that cost from cold, so pointing them at one shared directory is
        the single easiest latency win for anything that starts a fresh process.
        min_image_tokens, max_image_tokens: override the package's Qwen2-VL processor
        image-token bounds (default: the package's own values from
        ``gme_openvino_config.json``). This is the single most effective image/fused
        latency knob: attention cost grows with the visual token count (README S6.4-6.5),
        so capping ``max_image_tokens`` trades resolution for latency. Unlike
        ``max_length`` below, this needs no re-export -- both language and visual IRs
        accept any sequence length.
        max_length: override the package's tokenizer truncation length (default: the
        package's own value, e.g. 1800). The language IR has a fully dynamic sequence
        dimension, so this can be raised or lowered freely with no re-export --
        unlike the C++ runtime, where it is baked into a tokenizer IR at export time.
        dynamic_quantization_threshold: optional GPU activation-row threshold. Setting
        it to 0 enables the plugin's long-context RMSNorm-to-DynamicQuantize fusion,
        but also quantizes short rows that normally use the f16 pass-through. Use a
        dedicated long-context instance; the default preserves short-query accuracy.
        visual_dynamic_quantization_threshold: the corresponding visual-IR threshold.
        Setting it to 0 enables visual MVN-to-DynamicQuantize fusion independently of
        the language model, so text/query behavior remains unchanged. The fusion itself is
        bit-exact (verified down to L=256 patch rows), but 0 also disables the same
        short-row quantization bypass described above, and that part is only inert while
        ``min_image_tokens >= 256`` keeps every image at ``L = 4K >= 1024`` rows -- which
        the package default guarantees. Lowering ``min_image_tokens`` below 256 together
        with this flag does change image/fused outputs. See docs/14 S14.3.2b.
        Both thresholds are GPU-plugin properties: passing either to a non-GPU device
        raises rather than being silently dropped."""
        self.model_dir = Path(model_dir)
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
        self.max_length = processor_config["max_length"] if max_length is None else max_length
        if self.max_length < 1:
            raise ValueError(f"max_length must be positive, got {self.max_length}")
        self.processor = AutoProcessor.from_pretrained(
            str(self.model_dir),
            min_pixels=min_image_tokens * IMAGE_FACTOR * IMAGE_FACTOR,
            max_pixels=max_image_tokens * IMAGE_FACTOR * IMAGE_FACTOR,
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
        if fp32_math is None:
            fp32_math = precision == "fp32"
        compile_config = {ov.properties.hint.inference_precision: ov.Type.f32} if fp32_math else {}
        compile_config.update(self._stream_config(streams))
        language_compile_config = dict(compile_config)
        visual_compile_config = dict(compile_config)
        # GPU_DYNAMIC_QUANTIZATION_THRESHOLD only exists in the GPU plugin: the CPU plugin
        # rejects it outright ("NotFound: Unsupported property"), so handing it over would
        # turn an inapplicable tuning knob into a hard compile failure. Rejecting it here
        # instead of dropping it silently keeps an explicitly requested knob from being
        # ignored without the caller noticing. Callers that sweep several devices should
        # pass the threshold only for the GPU ones (see 04_validate_python.py).
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
        # Per-sample drops padding work and overlaps across CPU streams; a padded
        # call amortizes the GPU's per-submission overhead. See the class docstring.
        # This is a name-based heuristic, not a query of what AUTO/MULTI/HETERO
        # actually resolve to: only a device string that is (or starts with) "CPU"
        # picks per_sample; anything else, including meta-devices that might select
        # CPU underneath, defaults to padded. Pass batch_mode explicitly for those
        # if the CPU-side behavior matters to you.
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
        """True if `device` is a real device or a device OpenVINO otherwise accepts.

        `core.available_devices` only lists concrete plugins with detected hardware
        (e.g. ``["CPU", "GPU"]``), so a strict membership check rejects every legal
        multi-device string: ``"AUTO"``, ``"AUTO:CPU"``, ``"MULTI:CPU,GPU"``,
        ``"HETERO:GPU,CPU"``, ``"BATCH:GPU(4)"``, and a device index like
        ``"GPU.0"``. All were verified here to `core.compile_model()` successfully
        against this package's language IR. Rather than reimplement OpenVINO's
        device-string grammar, this only recognizes the plain-device and
        known-meta-device-prefix cases and otherwise defers to `compile_model`'s
        own error -- good enough to catch the common typo (e.g. `"gpu"` lowercase)
        without blocking a legitimate config this class has never been taught about.

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
    def _is_gpu_device(device: str) -> bool:
        """True only for a plain GPU device string, e.g. ``"GPU"`` or ``"GPU.1"``.

        Deliberately conservative and, like `batch_mode="auto"`, name-based rather than a
        query of what a meta-device resolves to: ``"AUTO"`` may well pick the GPU, but the
        property is forwarded to whichever plugin AUTO settles on, so treating it as GPU
        would reintroduce exactly the CPU-plugin rejection this guards against. Anything
        other than a plain GPU string must set the threshold on an explicit ``"GPU"``
        instance instead.
        """
        return device.split(":", 1)[0].split(".", 1)[0].upper() == "GPU"

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
    def _instruction(instruction: str | None, is_query: bool) -> str:  # noqa: ARG004
        """The system instruction for a prompt.

        An explicit ``instruction`` is honoured on either side; without one the
        default is used. ``is_query`` stays in the signature so a caller still
        reads as query/document, but no longer suppresses a document-side
        instruction -- the asymmetry now lives in what each caller passes (a query
        may carry a task instruction, a document usually passes ``None`` and so
        keeps the default). This is what lets the fused corpus path opt into a
        dedicated instruction without disturbing the text path, which passes none.
        """
        return instruction if instruction is not None else DEFAULT_INSTRUCTION

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

    def embed(
        self,
        texts: Sequence[str | None] | None = None,
        images: Sequence[Image.Image | None] | None = None,
        is_query: bool = True,
        instruction: str | None = None,
    ) -> np.ndarray:
        """Encode exactly one batch, the way official GME's ``embed()`` does.

        This is the primitive the chunked entry points call: no ``batch_size``, no
        progress bar, one processor invocation for the whole list. Either argument
        may be omitted, and ``images`` may be a list of ``None`` (official uses that
        to mean text-only), but an image list must be all-images or all-``None`` --
        upstream documents the same constraint ("all examples in the same batch are
        consistent") and simply crashes on a mixed list, so raising is strictly
        better while supporting the identical input surface.
        """
        text_values = None if texts is None else list(texts)
        image_values = None if images is None else list(images)
        if image_values is not None and any(image is None for image in image_values):
            if not all(image is None for image in image_values):
                raise ValueError(
                    "an image batch must be either all images or all None; official GME "
                    "requires every example in a batch to be consistent"
                )
            image_values = None  # official: `input_images = None` for a text-only batch
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
            # Official zips texts with images, so the shorter list wins. It relies on
            # that for its trailing partial batch (`none_batch` is a full batch_size
            # of None); keep the same rule instead of rejecting it.
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
        """Chunk into ``batch_size`` groups and concatenate, like official GME.

        Chunking is a memory knob only. Each row is computed from its own sample, so
        the concatenation of the chunks is the same array the single-chunk call
        returns -- 07_validate_batch.py asserts that bit-exactly.
        """
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
        images: Image.Image | Sequence[Image.Image],
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
        images: Image.Image | Sequence[Image.Image] | None = None,
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
        """Text encoding under the sentence-transformers/MTEB name.

        ``prompt_name`` exists because MTEB passes it; official GME accepts and
        ignores it too (GME selects its prompt with ``is_query``/``instruction``).
        """
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