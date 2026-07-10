# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Shared utilities for OpenVINO model conversion and loading for multimodal embedding handlers.

This module provides common functionality for converting PyTorch models to OpenVINO IR format
and loading them for inference. It supports the conversion pipeline for multimodal embedding
models that typically have separate text and image encoders.

Key functions:
- check_and_convert_openvino_models: Handles model conversion if needed
- load_openvino_models: Loads compiled OpenVINO models for inference

The utilities ensure efficient model conversion by checking for existing IR files
and only converting when necessary, reducing startup time for subsequent runs.
"""
import gc
import math
import os
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Dict

import numpy as np
import openvino as ov

from ...utils import logger


@dataclass
class BatchMetadata:
    """Metadata for async batch inference."""

    batch_idx: int
    samples_in_batch: int


def check_and_convert_openvino_models(
    model_key, model_loader, tokenizer_loader, convert_func, ov_models_dir):
    """
    Check if OpenVINO IR models exist and convert them if necessary.
    
    This function manages the OpenVINO conversion pipeline by checking for existing
    IR model files and performing conversion only when needed. It handles both
    image and text encoder models typical in multimodal embedding architectures.
    
    Args:
        model_key: Unique identifier for the model (used in filenames)
        model_loader: Callable that returns (model, _, preprocess) tuple
        tokenizer_loader: Callable that returns the tokenizer
        convert_func: Function to perform the actual OpenVINO conversion
        ov_models_dir: Directory to store OpenVINO IR model files
        
    Returns:
        Tuple of (image_encoder_path, text_encoder_path) as strings
        
    Note:
        The function creates the models directory if it doesn't exist and
        cleans up temporary models after conversion to free memory.
    """
    ov_models_path = Path(ov_models_dir)
    ov_models_path.mkdir(parents=True, exist_ok=True)
    image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
    text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"

    if not image_encoder_path.exists() or not text_encoder_path.exists():
        logger.info(
            f"OpenVINO models not found for {model_key}. Converting to OpenVINO format..."
        )
        
        # Handle the case where model and tokenizer loaders are None
        # This happens when using Optimum Intel which handles loading internally
        if model_loader is not None and tokenizer_loader is not None:
            # Load model and tokenizer for conversion
            model, _, _ = model_loader()
            tokenizer = tokenizer_loader()
            
            # Call the convert function with the loaded model and tokenizer
            convert_func(ov_models_dir, model, tokenizer)
            
            del model
            gc.collect()
        else:
            # For Optimum Intel conversion, pass None for model and tokenizer
            # The conversion function will handle model loading internally
            convert_func(ov_models_dir, None, None)
    return str(image_encoder_path), str(text_encoder_path)


def _enable_model_cache(core, image_encoder_path, text_encoder_path, device=None):
    """
    Enable OpenVINO model caching on the given Core instance.

    Compiling models for the NPU can take a long time (graph compilation
    happens on every startup). OpenVINO can persist the compiled blob and
    reuse it on subsequent runs by setting the ``CACHE_DIR`` property.

    Caching is **NPU-only by default**. On GPU/CPU it is left disabled
    because importing a GPU-compiled cache blob under throughput/AUTO-stream
    configuration can make the plugin over-allocate device memory and raise
    ``std::bad_alloc`` when the infer-request queue is created; a fresh
    compile on those devices is fast and avoids the problem. The default can
    be overridden with ``OV_ENABLE_MODEL_CACHE``:
    - ``1``/``true``/``yes``/``on``  -> force-enable on any device.
    - ``0``/``false``/``no``/``off`` -> force-disable on any device.

    The cache directory is resolved without hardcoding any path:
    - ``OV_CACHE_DIR`` / ``EMBEDDING_OV_CACHE_DIR`` env var, when set, wins.
    - Otherwise it is derived from the directory that holds the IR files
      (i.e. the configured OpenVINO models directory) as an ``ov_cache``
      subdirectory, so it persists alongside the IR on the same volume.

    Returns the resolved cache directory as a string, or ``None`` if caching
    was disabled or could not be enabled.
    """
    enable_flag = (os.getenv("OV_ENABLE_MODEL_CACHE") or "").strip().lower()
    device_upper = (device or "").upper()
    is_npu = device_upper.startswith("NPU")

    if enable_flag in {"0", "false", "no", "off"}:
        logger.info("OpenVINO model caching disabled via OV_ENABLE_MODEL_CACHE.")
        return None
    if enable_flag not in {"1", "true", "yes", "on"} and not is_npu:
        # Default policy: cache only on NPU. GPU/CPU cache import can trigger
        # std::bad_alloc, and their compile is cheap enough to skip caching.
        logger.info(
            "OpenVINO model caching skipped for device '%s' (enabled only for NPU by "
            "default; set OV_ENABLE_MODEL_CACHE=1 to force-enable).",
            device or "unknown",
        )
        return None

    cache_dir = os.getenv("OV_CACHE_DIR") or os.getenv("EMBEDDING_OV_CACHE_DIR")
    if not cache_dir:
        ir_path = image_encoder_path or text_encoder_path
        if not ir_path:
            return None
        cache_dir = str(Path(ir_path).resolve().parent / "ov_cache")

    try:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        core.set_property({"CACHE_DIR": cache_dir})
        logger.info("OpenVINO model caching enabled. CACHE_DIR=%s", cache_dir)
        return cache_dir
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning(
            "Could not enable OpenVINO model caching at %s: %s. "
            "Continuing without cache (compilation will run on every startup).",
            cache_dir,
            exc,
        )
        return None


def _resolve_static_shape(model_input, shape_hints=None):
    """
    Derive a fully static shape from a model input's partial shape.

    For each dimension:
    - If the dimension is already static, keep the model's own value.
    - If the dimension is dynamic, use the corresponding value from
      *shape_hints* (when provided and long enough) or fall back to 1.

    Args:
        model_input: An ``ov.Output`` obtained via ``model.input()``.
        shape_hints: Optional tuple/list of ints whose positional values
            are used for dynamic dimensions.

    Returns:
        A list of ints representing the resolved static shape.
    """
    partial = model_input.get_partial_shape()
    static_shape = []
    for idx, dim in enumerate(partial):
        if dim.is_static:
            static_shape.append(dim.get_length())
        elif shape_hints is not None and idx < len(shape_hints):
            static_shape.append(shape_hints[idx])
        else:
            static_shape.append(1)
    return static_shape


def load_openvino_models(
    image_encoder_path, text_encoder_path, device,
    reshape_shape=(1, 3, 224, 224), text_reshape_shape=None
):
    """
    Load and compile OpenVINO IR models for inference.
    
    This function loads the pre-converted OpenVINO IR models for both image
    and text encoders and compiles them for the specified target device.
    Uses the same pattern as the detector for thread-safe parallel processing.
    
    Args:
        image_encoder_path: Path to the image encoder IR model file (.xml)
        text_encoder_path: Path to the text encoder IR model file (.xml)  
        device: Target device for inference (e.g., "CPU", "GPU", "NPU")
        reshape_shape: Shape hints for the image encoder input (default: (1, 3, 224, 224)).
            Static dimensions in the model are preserved; hints are used only
            for dynamic dimensions.
        text_reshape_shape: Shape hints for the text encoder input (e.g., (1, 77)).
            When None, dynamic dimensions default to 1.

    Returns:
        Tuple of (compiled_image_encoder, compiled_text_encoder) ready for inference
        
    Note:
        The returned models are compiled and ready for thread-safe inference using
        infer_new_request() method, similar to the detector implementation.
    """
    core = ov.Core()
    _enable_model_cache(core, image_encoder_path, text_encoder_path, device)

    def _resolve_int_env(keys, default_value):
        for key in keys:
            value = os.getenv(key)
            if not value:
                continue
            try:
                return max(1, int(value))
            except ValueError:
                logger.warning(f"Ignoring non-integer value for {key}: {value}")
        return default_value

    performance_mode_env = os.getenv("OV_PERFORMANCE_MODE") or os.getenv(
        "OPENVINO_PERFORMANCE_MODE"
    )
    requested_mode = (performance_mode_env or "LATENCY").strip().upper()
    mode_aliases = {
        "THROUGHPUT": "THROUGHPUT",
        "LATENCY": "LATENCY",
        "CUMULATIVE_THROUGHPUT": "CUMULATIVE_THROUGHPUT",
        "CUMULATIVE": "CUMULATIVE_THROUGHPUT",
    }
    performance_mode = mode_aliases.get(requested_mode)
    if performance_mode is None:
        logger.warning(
            "Unknown OV_PERFORMANCE_MODE '%s'. Falling back to LATENCY mode.",
            requested_mode,
        )
        performance_mode = "LATENCY"

    logger.info("Using OpenVINO performance mode: %s", performance_mode)

    device_upper = (device or "").upper()
    needs_static_shapes = device_upper.startswith("GPU") or device_upper.startswith("NPU")

    if performance_mode == "LATENCY":
        logger.info("Latency mode selected; compiling with default OpenVINO settings (no overrides).")
        if needs_static_shapes:
            image_encoder_model = core.read_model(image_encoder_path)
            image_input = image_encoder_model.input()
            static_image_shape = _resolve_static_shape(image_input, reshape_shape)
            logger.info(
                f"Device {device} requires static shapes: reshaping image encoder to {static_image_shape}"
            )
            image_encoder_model.reshape({image_input.get_any_name(): static_image_shape})
            ov_image_encoder = core.compile_model(image_encoder_model, device)

            text_encoder_model = core.read_model(text_encoder_path)
            text_input = text_encoder_model.input()
            if text_input.get_partial_shape().is_dynamic:
                static_text_shape = _resolve_static_shape(text_input, text_reshape_shape)
                logger.info(
                    f"Device {device} requires static shapes: reshaping text encoder to {static_text_shape}"
                )
                text_encoder_model.reshape({text_input.get_any_name(): static_text_shape})
            ov_text_encoder = core.compile_model(text_encoder_model, device)
        else:
            ov_image_encoder = core.compile_model(image_encoder_path, device)
            ov_text_encoder = core.compile_model(text_encoder_path, device)
    else:
        total_cpus = max(1, os.cpu_count() or 1)
        base_worker_target = max(1, total_cpus // 4)
        default_requests = base_worker_target

        perf_hint_requests = _resolve_int_env(
            ["OV_PERFORMANCE_HINT_NUM_REQUESTS", "PERFORMANCE_HINT_NUM_REQUESTS"],
            default_requests,
        )

        config = {
            "PERFORMANCE_HINT": performance_mode,
            "PERFORMANCE_HINT_NUM_REQUESTS": perf_hint_requests,
            "NUM_STREAMS": "AUTO",
        }

        device_upper = (device or "").upper()
        if device_upper in {"CPU", "AUTO"} or device_upper.startswith("CPU") or "CPU" in device_upper:
            target_cores = max(1, int(total_cpus * 0.8))

            max_workers_env = os.getenv("MAX_PARALLEL_WORKERS")
            if max_workers_env:
                try:
                    pipeline_workers = max(1, int(max_workers_env))
                except ValueError:
                    pipeline_workers = base_worker_target
            else:
                pipeline_workers = base_worker_target

            pipeline_workers = min(pipeline_workers, perf_hint_requests)

            inference_threads_env = os.getenv("OV_INFERENCE_NUM_THREADS")
            if inference_threads_env:
                try:
                    inference_threads = max(1, int(inference_threads_env))
                except ValueError:
                    inference_threads = max(1, min(total_cpus * 2, target_cores * 2))
            else:
                inference_threads = max(1, min(total_cpus * 2, target_cores * 2))

            num_streams_env = os.getenv("OV_NUM_STREAMS")
            if num_streams_env:
                try:
                    num_streams = max(1, int(num_streams_env))
                except ValueError:
                    num_streams = max(1, min(target_cores, pipeline_workers * 2))
            else:
                num_streams = max(1, min(target_cores, pipeline_workers * 2))

            cpu_specific_config = {
                "INFERENCE_NUM_THREADS": inference_threads,
                "NUM_STREAMS": num_streams,
                "AFFINITY": "CORE",
                "ENABLE_HYPER_THREADING": "YES",
            }

            supported_cpu_properties = set()
            for candidate in {device, "CPU"}:
                try:
                    if candidate:
                        supported_cpu_properties.update(
                            core.get_property(candidate, "SUPPORTED_PROPERTIES")
                        )
                except Exception as exc:  # pragma: no cover - diagnostic path
                    logger.debug(f"Unable to query supported properties for {candidate}: {exc}")

            logger.info(f"cpu_specific_config: {cpu_specific_config}")
            for prop_key, prop_value in cpu_specific_config.items():
                if prop_key in supported_cpu_properties:
                    logger.info(
                        "Setting OpenVINO CPU property '%s': %s", prop_key, prop_value
                    )
                    config[prop_key] = prop_value
                else:
                    logger.info(
                        "Skipping unsupported OpenVINO CPU property '%s'", prop_key
                    )
            ov_image_encoder = core.compile_model(image_encoder_path, device, config)
            ov_text_encoder = core.compile_model(text_encoder_path, device, config)
        else:
            image_encoder_model = core.read_model(image_encoder_path)
            image_input = image_encoder_model.input()
            static_image_shape = _resolve_static_shape(image_input, reshape_shape)
            logger.info(
                f"Accelerator configuration ({device}): Reshaping image encoder to {static_image_shape} - {config}"
            )
            image_encoder_model.reshape({image_input.get_any_name(): static_image_shape})
            ov_image_encoder = core.compile_model(image_encoder_model, device, config)

            text_encoder_model = core.read_model(text_encoder_path)
            text_input = text_encoder_model.input()
            if text_input.get_partial_shape().is_dynamic:
                static_text_shape = _resolve_static_shape(text_input, text_reshape_shape)
                logger.info(
                    f"Accelerator ({device}): Reshaping text encoder to {static_text_shape}"
                )
                text_encoder_model.reshape({text_input.get_any_name(): static_text_shape})
            ov_text_encoder = core.compile_model(text_encoder_model, device, config)

    logger.info(
        "Loaded image encoder: inputs=%s, outputs=%s",
        len(ov_image_encoder.inputs),
        len(ov_image_encoder.outputs),
    )
    logger.info(
        "Loaded text encoder: inputs=%s, outputs=%s",
        len(ov_text_encoder.inputs),
        len(ov_text_encoder.outputs),
    )

    return ov_image_encoder, ov_text_encoder


def infer_with_batch_support(
    compiled_model: ov.CompiledModel,
    model_inputs: Dict[Any, Any],
    output_index: int = 0,
) -> np.ndarray:
    """
    Run OpenVINO inference while handling static batch-size constraints.

    For static-shape models (common on NPU/GPU), this helper splits oversized
    batches into chunks and pads undersized chunks to the compiled batch size,
    then slices outputs back to the original request size.
    """
    if not model_inputs:
        raise ValueError("model_inputs must not be empty")

    def _to_numpy(value: Any) -> np.ndarray:
        if isinstance(value, np.ndarray):
            return value
        if hasattr(value, "detach"):
            return value.detach().cpu().numpy()
        return np.asarray(value)

    normalized_inputs: Dict[Any, np.ndarray] = {
        key: _to_numpy(value) for key, value in model_inputs.items()
    }
    first_input = next(iter(normalized_inputs.values()))
    if first_input.ndim == 0:
        result = compiled_model.infer_new_request(normalized_inputs)
        return result[compiled_model.outputs[output_index]]

    total_samples = int(first_input.shape[0])
    batch_dim = compiled_model.inputs[0].get_partial_shape()[0]

    if not batch_dim.is_static:
        result = compiled_model.infer_new_request(normalized_inputs)
        return result[compiled_model.outputs[output_index]]

    compiled_batch_size = max(1, int(batch_dim.get_length()))
    if total_samples == compiled_batch_size:
        result = compiled_model.infer_new_request(normalized_inputs)
        return result[compiled_model.outputs[output_index]]

    def _pad_to_batch(arr: np.ndarray, expected_batch_size: int) -> np.ndarray:
        current = int(arr.shape[0])
        if current >= expected_batch_size:
            return arr
        pad_width = [(0, expected_batch_size - current)] + [(0, 0)] * (arr.ndim - 1)
        return np.pad(arr, pad_width, mode="constant")

    outputs = []
    for start in range(0, total_samples, compiled_batch_size):
        end = min(start + compiled_batch_size, total_samples)
        samples_in_chunk = end - start

        chunk_inputs = {
            key: value[start:end] for key, value in normalized_inputs.items()
        }
        if samples_in_chunk < compiled_batch_size:
            chunk_inputs = {
                key: _pad_to_batch(value, compiled_batch_size)
                for key, value in chunk_inputs.items()
            }

        chunk_result = compiled_model.infer_new_request(chunk_inputs)
        chunk_output = chunk_result[compiled_model.outputs[output_index]]
        outputs.append(chunk_output[:samples_in_chunk])

    return np.concatenate(outputs, axis=0)


class AsyncBatchInference:
    """
    Reusable async batch inference for OpenVINO models.

    Args:
        compiled_model: Compiled OpenVINO model.
        batch_size: Number of samples per batch (default: 32).
        embedding_dim: Output embedding dimension (default: 512).
    """

    def __init__(
        self,
        compiled_model: ov.CompiledModel,
        embedding_dim: int = 512,
        preprocess_shape: tuple = (1, 3, 224, 224),
    ):
        self.compiled_model = compiled_model
        self.batch_size = preprocess_shape[0] if preprocess_shape is not None else 64
        self.embedding_dim = embedding_dim
        self.async_queue = ov.AsyncInferQueue(compiled_model)
        self.preprocess_shape = preprocess_shape

    def infer_stream(self, batch_generator, total_images):
        final_output = np.empty((total_images, self.embedding_dim), dtype=np.float32)

        submitted = 0
        completed = 0

        def callback(request, userdata):
            nonlocal completed

            start = userdata["start"]
            count = userdata["count"]

            out = request.output_tensors[0].data
            final_output[start:start+count] = out[:count]

            completed += count

        self.async_queue.set_callback(callback)

        for batch in batch_generator:

            count = batch.shape[0]

            if count < self.batch_size:
                padded = np.zeros(self.preprocess_shape, dtype=np.float32)
                padded[:count] = batch
                batch = padded

            while not self.async_queue.is_ready():
                time.sleep(0.001)

            self.async_queue.start_async(
                {0: batch},
                userdata={"start": submitted, "count": count}
            )

            submitted += count

        self.async_queue.wait_all()

        return final_output

    def infer(self, images: np.ndarray) -> np.ndarray:
        """
        Run async batch inference on preprocessed images.

        Args:
            images: Preprocessed images as a numpy array [N, C, H, W].

        Returns:
            Embeddings as numpy array [N, embedding_dim].
        """
        total_images = images.shape[0]
        num_batches = math.ceil(total_images / self.batch_size)
        # TODO: check np.float16 option & accuracy
        final_output = np.empty((total_images, self.embedding_dim), dtype=np.float32)

        def response_callback(request, userdata):
            batch_idx = userdata.batch_idx
            samples_in_batch = userdata.samples_in_batch
            out = request.output_tensors[0].data
            start = batch_idx * self.batch_size
            end = start + samples_in_batch
            final_output[start:end] = out[:samples_in_batch]

        self.async_queue.set_callback(response_callback)

        for i in range(num_batches):

            batch_np = images[i * self.batch_size : (i + 1) * self.batch_size]

            samples_in_batch = batch_np.shape[0]
            if samples_in_batch < self.batch_size:
                # For uneven batch sizes, Pad with zeros to fill the batch
                padded = np.zeros(self.preprocess_shape, dtype=np.float32)
                padded[:samples_in_batch] = batch_np
                batch_np = padded

            metadata = BatchMetadata(batch_idx=i, samples_in_batch=samples_in_batch)

            if not self.async_queue.is_ready():
                self.async_queue.wait_all()

            self.async_queue.start_async({0: batch_np}, userdata=metadata)

        self.async_queue.wait_all()

        return final_output
