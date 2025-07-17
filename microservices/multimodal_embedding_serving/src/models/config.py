# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model configuration registry.
Defines all supported models and their configurations.
Based on the MobileCLIP notebook model configurations.
"""

import os
from pathlib import Path


def default_image_probs(image_features, text_features):
    """Default similarity calculation for CLIP-style models."""
    image_probs = (100.0 * text_features @ image_features.T).softmax(dim=-1)
    return image_probs


def blip2_image_probs(image_features, text_features):
    """BLIP2-specific similarity calculation."""
    image_probs = image_features[:, 0, :] @ text_features[:, 0, :].t()
    return image_probs


# Model configurations based on the MobileCLIP notebook
MODEL_CONFIGS = {
    "MobileCLIP": {
        "mobileclip_s0": {
            "model_name": "mobileclip_s0",
            "pretrained": "checkpoints/mobileclip_s0.pt",
            "url": "https://docs-assets.developer.apple.com/ml-research/datasets/mobileclip/mobileclip_s0.pt",
            "image_size": 256,
            "handler_class": "MobileCLIPHandler",
            "image_probs": default_image_probs,
        },
        "mobileclip_s1": {
            "model_name": "mobileclip_s1",
            "pretrained": "checkpoints/mobileclip_s1.pt",
            "url": "https://docs-assets.developer.apple.com/ml-research/datasets/mobileclip/mobileclip_s1.pt",
            "image_size": 256,
            "handler_class": "MobileCLIPHandler",
            "image_probs": default_image_probs,
        },
        "mobileclip_s2": {
            "model_name": "mobileclip_s2",
            "pretrained": "checkpoints/mobileclip_s2.pt",
            "url": "https://docs-assets.developer.apple.com/ml-research/datasets/mobileclip/mobileclip_s2.pt",
            "image_size": 256,
            "handler_class": "MobileCLIPHandler",
            "image_probs": default_image_probs,
        },
        "mobileclip_b": {
            "model_name": "mobileclip_b",
            "pretrained": "checkpoints/mobileclip_b.pt",
            "url": "https://docs-assets.developer.apple.com/ml-research/datasets/mobileclip/mobileclip_b.pt",
            "image_size": 224,
            "handler_class": "MobileCLIPHandler",
            "image_probs": default_image_probs,
        },
        "mobileclip_blt": {
            "model_name": "mobileclip_b",
            "pretrained": "checkpoints/mobileclip_blt.pt",
            "url": "https://docs-assets.developer.apple.com/ml-research/datasets/mobileclip/mobileclip_blt.pt",
            "image_size": 224,
            "handler_class": "MobileCLIPHandler",
            "image_probs": default_image_probs,
        },
    },
    "CLIP": {
        "clip-vit-b-32": {
            "model_name": "ViT-B-32",
            "pretrained": "laion2b_s34b_b79k",
            "image_size": 224,
            "handler_class": "CLIPHandler",
            "image_probs": default_image_probs,
        },
        "clip-vit-b-16": {
            "model_name": "ViT-B-16",
            "pretrained": "openai",
            "image_size": 224,
            "handler_class": "CLIPHandler",
            "image_probs": default_image_probs,
        },
        "clip-vit-l-14": {
            "model_name": "ViT-L-14",
            "pretrained": "datacomp_xl_s13b_b90k",
            "image_size": 224,
            "handler_class": "CLIPHandler",
            "image_probs": default_image_probs,
        },
        "clip-vit-h-14": {
            "model_name": "ViT-H-14",
            "pretrained": "laion2b_s32b_b79k",
            "image_size": 224,
            "handler_class": "CLIPHandler",
            "image_probs": default_image_probs,
        },
    },
    "SigLIP": {
        "siglip-vit-b-16": {
            "model_name": "ViT-B-16-SigLIP",
            "pretrained": "webli",
            "image_size": 224,
            "handler_class": "SigLIPHandler",
            "image_probs": default_image_probs,
        },
        "siglip-vit-l-16": {
            "model_name": "ViT-L-16-SigLIP-256",
            "pretrained": "webli",
            "image_size": 256,
            "handler_class": "SigLIPHandler",
            "image_probs": default_image_probs,
        },
    },
    "Blip2": {
        "blip2_feature_extractor": {
            "model_name": "blip2_feature_extractor",
            "pretrained": "pretrain_vitL",
            "image_size": 224,
            "handler_class": "BLIP2Handler",
            "image_probs": blip2_image_probs,
        },
        "blip2_transformers": {
            "model_name": "blip2_feature_extractor",
            "pretrained": "pretrain",
            "image_size": 224,
            "handler_class": "BLIP2TransformersHandler",
            "image_probs": blip2_image_probs,
        },
        "blip2_transformers_vitL": {
            "model_name": "blip2_feature_extractor",
            "pretrained": "pretrain_vitL",
            "image_size": 224,
            "handler_class": "BLIP2TransformersHandler",
            "image_probs": blip2_image_probs,
        },
    },
}


def get_model_config(model_id: str, device=None, ov_models_dir=None, use_openvino=None) -> dict:
    """
    Get model configuration by model ID with optional parameter overrides.
    
    Args:
        model_id (str): Model identifier in format "type/name" or just "name"
        device (str, optional): Device for inference (e.g., "CPU")
        ov_models_dir (str, optional): Directory for OpenVINO models
        use_openvino (bool, optional): Whether to use OpenVINO
        
    Returns:
        dict: Model configuration dictionary
        
    Raises:
        ValueError: If model is not found
    """
    # Handle both "type/name" and "name" formats
    if "/" in model_id:
        model_type, model_name = model_id.split("/", 1)
    else:
        # Search for model name across all types
        for model_type, models in MODEL_CONFIGS.items():
            if model_id in models:
                model_name = model_id
                break
        else:
            raise ValueError(f"Model {model_id} not found in any model type")
    
    if model_type not in MODEL_CONFIGS:
        raise ValueError(f"Model type {model_type} not supported")
    
    if model_name not in MODEL_CONFIGS[model_type]:
        raise ValueError(f"Model {model_name} not found in {model_type}")
    
    config = MODEL_CONFIGS[model_type][model_name].copy()
    
    # Add common configuration with user overrides or defaults
    config.update({
        "device": device or os.getenv("EMBEDDING_DEVICE", "CPU"),
        "ov_models_dir": ov_models_dir or os.getenv("EMBEDDING_OV_MODELS_DIR", "ov-models"),
        "use_openvino": (
            use_openvino 
            if use_openvino is not None 
            else os.getenv("EMBEDDING_USE_OV", "false").lower() == "true"
        ),
    })
    
    return config


def list_available_models() -> dict:
    """
    List all available models grouped by type.
    
    Returns:
        dict: Dictionary with model types as keys and list of model names as values
    """
    return {
        model_type: list(models.keys()) 
        for model_type, models in MODEL_CONFIGS.items()
    }


def get_default_model() -> str:
    """
    Get the default model ID.
    
    Returns:
        str: Default model ID
    """
    return os.getenv("MODEL_NAME", "CLIP/clip-vit-b-16")
