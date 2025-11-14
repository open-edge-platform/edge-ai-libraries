# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model configuration registry.

This module defines all supported models and their configurations for the
multimodal embedding serving system. It provides centralized configuration
management for various model architectures and their parameters.
"""

import os


def default_image_probs(image_features, text_features):
    """
    Default similarity calculation for CLIP-style models.
    
    Computes similarity scores between image and text features using cosine similarity
    scaled by a temperature factor of 100.
    
    Args:
        image_features: Image feature embeddings tensor
        text_features: Text feature embeddings tensor
        
    Returns:
        Softmax normalized similarity probabilities
    """
    image_probs = (100.0 * text_features @ image_features.T).softmax(dim=-1)
    return image_probs


def blip2_image_probs(image_features, text_features):
    """
    BLIP2-specific similarity calculation.
    
    Computes similarity using the first token features for both image and text,
    which is the standard approach for BLIP2 models.
    
    Args:
        image_features: Image feature embeddings tensor with shape [batch, seq_len, hidden_dim]  
        text_features: Text feature embeddings tensor with shape [batch, seq_len, hidden_dim]
        
    Returns:
        Similarity scores between image and text features
    """
    image_probs = image_features[:, 0, :] @ text_features[:, 0, :].t()
    return image_probs


# Model configurations for supported architectures
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
    "CN-CLIP": {
        "cn-clip-vit-b-16": {
            "model_name": "ViT-B-16",
            "pretrained": "",
            "image_size": 224,
            "handler_class": "CNClipHandler",
            "image_probs": default_image_probs,
        },
        "cn-clip-vit-l-14": {
            "model_name": "ViT-L-14",
            "pretrained": "",
            "image_size": 224,
            "handler_class": "CNClipHandler",
            "image_probs": default_image_probs,
        },
        "cn-clip-vit-h-14": {
            "model_name": "ViT-H-14",
            "pretrained": "",
            "image_size": 224,
            "handler_class": "CNClipHandler",
            "image_probs": default_image_probs,
        },
    },
    "SigLIP": {
        "siglip2-vit-b-16": {
            "model_name": "ViT-B-16-SigLIP2",
            "pretrained": "webli",
            "image_size": 224,
            "handler_class": "SigLIPHandler",
            "image_probs": default_image_probs,
        },
        "siglip2-vit-l-16": {
            "model_name": "ViT-L-16-SigLIP2-256",
            "pretrained": "webli",
            "image_size": 256,
            "handler_class": "SigLIPHandler",
            "image_probs": default_image_probs,
        },
        "siglip2-so400m-patch16-384": {
            "model_name": "ViT-SO400M-16-SigLIP2-384",
            "pretrained": "webli",
            "image_size": 384,
            "handler_class": "SigLIPHandler",
            "image_probs": default_image_probs,
        },
    },
    "Blip2": {
        "blip2_transformers": {
            "model_name": "blip2_feature_extractor",
            "pretrained": "pretrain",
            "image_size": 224,
            "handler_class": "BLIP2TransformersHandler",
            "image_probs": blip2_image_probs,
        },
    },
    "QwenText": {
        "qwen3-embedding-0.6b": {
            "hf_model_id": "Qwen/Qwen3-Embedding-0.6B",
            "handler_class": "QwenEmbeddingHandler",
            "max_length": 8192,
            "weight_format": "int8",
            "instruction_template": "Instruct: {task_description}\\nQuery:{query}",
            "task_description": "Given a web search query, retrieve relevant passages that answer the query",
            "modalities": ["text"],
            "trust_remote_code": True,
        },
        "qwen3-embedding-4b": {
            "hf_model_id": "Qwen/Qwen3-Embedding-4B",
            "handler_class": "QwenEmbeddingHandler",
            "max_length": 8192,
            "weight_format": "int8",
            "instruction_template": "Instruct: {task_description}\\nQuery:{query}",
            "task_description": "Given a web search query, retrieve relevant passages that answer the query",
            "modalities": ["text"],
            "trust_remote_code": True,
        },
        "qwen3-embedding-8b": {
            "hf_model_id": "Qwen/Qwen3-Embedding-8B",
            "handler_class": "QwenEmbeddingHandler",
            "max_length": 8192,
            "weight_format": "int8",
            "instruction_template": "Instruct: {task_description}\\nQuery:{query}",
            "task_description": "Given a web search query, retrieve relevant passages that answer the query",
            "modalities": ["text"],
            "trust_remote_code": True,
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
