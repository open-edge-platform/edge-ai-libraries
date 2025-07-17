# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Shared utilities for OpenVINO model conversion and loading for multimodal embedding handlers.
"""
from pathlib import Path
import gc
import openvino as ov


def check_and_convert_openvino_models(
    model_key, model_loader, tokenizer_loader, convert_func, ov_models_dir, logger
):
    """
    Check if OpenVINO IR models exist. If not, convert using the provided convert_func.
    Returns paths to image and text encoder IR models.
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
    Load OpenVINO IR models for image and text encoders.
    """
    core = ov.Core()
    ov_image_encoder = core.compile_model(image_encoder_path, device)
    ov_text_encoder = core.compile_model(text_encoder_path, device)
    return ov_image_encoder, ov_text_encoder
