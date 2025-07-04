#!/usr/bin/env python3
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SDK Examples for Multimodal Embedding Serving

This file demonstrates how to use the multimodal embedding serving 
microservice as an SDK for generating embeddings from text, images, 
and videos using different models.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the Python path for imports
src_path = Path(__file__).parent.parent
print(f"sys.path: {src_path}")
sys.path.insert(0, str(src_path))

from src.models import get_model_handler, list_available_models
from src.models.wrapper import EmbeddingModel


MODEL_TESTS = [
    ("CLIP/clip-vit-b-16", "A beautiful sunset over the ocean"),
    ("MobileCLIP/mobileclip_s0", "A red car on a mountain road"),
    ("SigLIP/siglip-vit-b-16", "A modern cityscape at night"),
    ("Blip2/blip2_feature_extractor", "A person riding a horse on the beach"),
]

OV_BASE_DIR = Path(__file__).parent.parent / "ov-models"


def example_list_available_models():
    """Example: List all available models"""
    print("=" * 50)
    print("Available Models:")
    print("=" * 50)
    
    models = list_available_models()
    for model_type, model_names in models.items():
        print(f"{model_type}:")
        for name in model_names:
            print(f"  - {name}")
    print()


def example_text_embedding():
    """Example: Generate text embeddings using CLIP"""
    print("=" * 50)
    print("Text Embedding Example (CLIP)")
    print("=" * 50)
    
    # Get CLIP handler
    handler = get_model_handler("CLIP/clip-vit-b-16")
    print(f"Model: {handler.model_config['model_name']}")
    
    # Load model (without OpenVINO conversion for this example)
    handler.load_model()
    
    # Create wrapper for application-level methods
    embedding_model = EmbeddingModel(handler)
    
    # Generate text embedding
    text = "A beautiful sunset over the ocean"
    embedding = embedding_model.embed_query(text)
    
    print(f"Text: '{text}'")
    print(f"Embedding shape: {len(embedding)} dimensions")
    print(f"First 5 values: {embedding[:5]}")
    print()


def example_mobileclip_text_embedding():
    """Example: Generate text embeddings using MobileCLIP"""
    print("=" * 50)
    print("Text Embedding Example (MobileCLIP)")
    print("=" * 50)
    
    # Get MobileCLIP handler
    handler = get_model_handler("MobileCLIP/mobileclip_s0")
    print(f"Model: {handler.model_config['model_name']}")
    
    # Load model
    handler.load_model()
    
    # Create wrapper
    embedding_model = EmbeddingModel(handler)
    
    # Generate text embedding
    text = "A red car on a mountain road"
    embedding = embedding_model.embed_query(text)
    
    print(f"Text: '{text}'")
    print(f"Embedding shape: {len(embedding)} dimensions")
    print(f"First 5 values: {embedding[:5]}")
    print()


def example_multiple_texts():
    """Example: Generate embeddings for multiple texts"""
    print("=" * 50)
    print("Multiple Text Embeddings Example")
    print("=" * 50)
    
    # Get handler
    handler = get_model_handler("CLIP/clip-vit-b-16")
    handler.load_model()
    
    embedding_model = EmbeddingModel(handler)
    
    # Multiple texts
    texts = [
        "A dog playing in the park",
        "A cat sleeping on a sofa",
        "A bird flying in the sky",
        "A fish swimming in the ocean"
    ]
    
    embeddings = embedding_model.embed_documents(texts)
    
    print(f"Generated embeddings for {len(texts)} texts:")
    for i, (text, embedding) in enumerate(zip(texts, embeddings)):
        print(f"{i+1}. '{text}' -> {len(embedding)} dimensions")
    print()


def example_model_comparison():
    """Example: Compare different models on the same text"""
    print("=" * 50)
    print("Model Comparison Example")
    print("=" * 50)
    
    text = "A modern cityscape at night"
    models_to_test = [
        "CLIP/clip-vit-b-16",
        "MobileCLIP/mobileclip_s0",
        "SigLIP/siglip-vit-b-16"
    ]
    
    print(f"Text: '{text}'")
    print()
    
    for model_name in models_to_test:
        try:
            handler = get_model_handler(model_name)
            handler.load_model()
            
            embedding_model = EmbeddingModel(handler)
            embedding = embedding_model.embed_query(text)
            
            print(f"{model_name}:")
            print(f"  Embedding dimensions: {len(embedding)}")
            print(f"  First 3 values: {embedding[:3]}")
            print()
            
        except Exception as e:
            print(f"{model_name}: Error - {e}")
            print()


def example_openvino_conversion():
    """Example: Convert model to OpenVINO format"""
    print("=" * 50)
    print("OpenVINO Conversion Example")
    print("=" * 50)
    
    # Get handler
    handler = get_model_handler("CLIP/clip-vit-b-16")
    print(f"Model: {handler.model_config['model_name']}")
    
    # Load model first
    handler.load_model()
    print("Model loaded successfully")
    
    # Convert to OpenVINO
    ov_models_dir = "/tmp/ov_models"
    os.makedirs(ov_models_dir, exist_ok=True)
    
    try:
        handler.convert_to_openvino(ov_models_dir)
        print(f"Model converted to OpenVINO format in: {ov_models_dir}")
        
        # Test with OpenVINO
        embedding_model = EmbeddingModel(handler)
        text = "Testing OpenVINO inference"
        embedding = embedding_model.embed_query(text)
        
        print(f"OpenVINO inference successful!")
        print(f"Text: '{text}'")
        print(f"Embedding shape: {len(embedding)} dimensions")
        
    except Exception as e:
        print(f"OpenVINO conversion failed: {e}")
    
    print()


def run_embedding_example(model_id, text, use_openvino=None, device=None, ov_models_dir=None):
    print("-" * 60)
    print(f"Model: {model_id}")
    print(f"Text: {text}")
    print(f"use_openvino: {use_openvino}, device: {device}, ov_models_dir: {ov_models_dir}")
    try:
        # Set OpenVINO model dir as required
        if use_openvino:
            model_name = model_id.replace("/", "_")
            ov_dir = OV_BASE_DIR / model_name
            ov_dir.mkdir(parents=True, exist_ok=True)
            ov_models_dir = str(ov_dir)
        
        # Handler creation with param overrides
        handler = get_model_handler(
            model_id,
            device=device,
            ov_models_dir=ov_models_dir,
            use_openvino=use_openvino,
        )
        
        # Load model (this will convert to OpenVINO if needed)
        handler.load_model()
        
        # If OpenVINO is requested but models don't exist, convert them
        if use_openvino and not handler.use_openvino:
            print("Converting model to OpenVINO format...")
            handler.convert_to_openvino(ov_models_dir)
            # Reload with OpenVINO enabled
            handler = get_model_handler(
                model_id,
                device=device,
                ov_models_dir=ov_models_dir,
                use_openvino=use_openvino,
            )
            handler.load_model()
        
        embedding_model = EmbeddingModel(handler)
        embedding = embedding_model.embed_query(text)
        print(f"✓ Success! Embedding shape: {len(embedding)} dimensions")
        print(f"  First 5 values: {embedding[:5]}")
        print(f"  Using {'OpenVINO' if handler.use_openvino else 'PyTorch'} inference")
    except Exception as e:
        print(f"✗ Error: {e}")
    print()


def example_all_models_native_and_openvino():
    print("=" * 50)
    print("All Model Types: Native and OpenVINO SDK Usage")
    print("=" * 50)
    for model_id, text in MODEL_TESTS:
        # Native (no OpenVINO)
        run_embedding_example(model_id, text, use_openvino=False)
        # OpenVINO (with explicit device and ov_models_dir)
        run_embedding_example(model_id, text, use_openvino=True, device="CPU")


def main():
    print("Multimodal Embedding Serving - SDK Examples")
    print("=" * 70)
    print()
    try:
        example_list_available_models()
        example_all_models_native_and_openvino()
        print("=" * 70)
        print("All examples completed successfully!")
    except Exception as e:
        print(f"Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
