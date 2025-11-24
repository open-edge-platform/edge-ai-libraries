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
from pathlib import Path
import gc
import os
import openvino as ov
from ...utils import logger

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


def load_openvino_models(image_encoder_path, text_encoder_path, device):
    """
    Load and compile OpenVINO IR models for inference.
    
    This function loads the pre-converted OpenVINO IR models for both image
    and text encoders and compiles them for the specified target device.
    Uses the same pattern as the detector for thread-safe parallel processing.
    
    Args:
        image_encoder_path: Path to the image encoder IR model file (.xml)
        text_encoder_path: Path to the text encoder IR model file (.xml)  
        device: Target device for inference (e.g., "CPU", "GPU", "AUTO")
        
    Returns:
        Tuple of (compiled_image_encoder, compiled_text_encoder) ready for inference
        
    Note:
        The returned models are compiled and ready for thread-safe inference using
        infer_new_request() method, similar to the detector implementation.
    """
    core = ov.Core()

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

    if performance_mode == "LATENCY":
        logger.info("Latency mode selected; compiling with default OpenVINO settings (no overrides).")
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
