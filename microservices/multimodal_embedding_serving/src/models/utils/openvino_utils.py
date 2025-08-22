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
        # Load model and tokenizer for conversion
        model, _, _ = model_loader()
        tokenizer = tokenizer_loader()
        
        # Call the convert function with the loaded model and tokenizer
        # Pass them as parameters to the convert function
        convert_func(ov_models_dir, model, tokenizer)
        
        del model
        gc.collect()
    return str(image_encoder_path), str(text_encoder_path)


def load_openvino_models(image_encoder_path, text_encoder_path, device):
    """
    Load and compile OpenVINO IR models for inference.
    
    This function loads the pre-converted OpenVINO IR models for both image
    and text encoders and compiles them for the specified target device.
    
    Args:
        image_encoder_path: Path to the image encoder IR model file (.xml)
        text_encoder_path: Path to the text encoder IR model file (.xml)  
        device: Target device for inference (e.g., "CPU", "GPU", "AUTO")
        
    Returns:
        Tuple of (compiled_image_encoder, compiled_text_encoder) ready for inference
        
    Note:
        The returned models are compiled and ready for immediate inference.
        They should be used for actual model inference rather than the IR files.
    """
    core = ov.Core()
    ov_image_encoder = core.compile_model(image_encoder_path, device)
    ov_text_encoder = core.compile_model(text_encoder_path, device)
    return ov_image_encoder, ov_text_encoder
