#!/usr/bin/env python3
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Server Examples for Multimodal Embedding Serving

This module demonstrates how to start and interact with the FastAPI server
for multimodal embedding generation. It provides complete examples for:

- Starting the FastAPI server with proper configuration
- Making API calls for different input types (text, images, videos)
- Handling responses and error conditions
- Testing various model configurations

The examples cover practical usage scenarios including text embedding generation,
image processing from URLs and base64 data, and video frame extraction workflows.
These examples serve as a comprehensive guide for integrating the embedding
service into larger applications and systems.

Usage:
    Run this script directly to see server interaction examples, or import
    specific functions for use in your own applications.
"""

import os
import subprocess
import time
import requests
import json
from pathlib import Path


def start_server_example():
    """
    Example: Start the FastAPI server with configuration.
    
    Demonstrates how to properly configure and start the multimodal embedding
    server with environment variables. Shows the complete startup process
    including model loading and health checks.
    
    Note:
        This is a blocking operation that starts the server process.
        Use in testing or development scenarios where manual server
        control is needed.
    """
    print("=" * 50)
    print("Starting FastAPI Server Example")
    print("=" * 50)

    # Set environment variables for the server
    os.environ["EMBEDDING_MODEL_NAME"] = "CLIP/clip-vit-b-16"
    os.environ["EMBEDDING_USE_OV"] = "false"
    os.environ["EMBEDDING_DEVICE"] = "CPU"

    print("Environment variables set:")
    print(f"  EMBEDDING_MODEL_NAME: {os.environ.get('EMBEDDING_MODEL_NAME')}")
    print(f"  EMBEDDING_USE_OV: {os.environ.get('EMBEDDING_USE_OV')}")
    print(f"  EMBEDDING_DEVICE: {os.environ.get('EMBEDDING_DEVICE')}")
    print()

    print("To start the server manually, run:")
    print("  uvicorn app:app --host 0.0.0.0 --port 8080")
    print()

    print("Or use the launcher:")
    print("  python launcher.py")
    print()


def test_server_endpoints():
    """Example: Test server endpoints (assumes server is running)"""
    print("=" * 50)
    print("Testing Server Endpoints")
    print("=" * 50)

    base_url = "http://localhost:8080"

    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/health")
        print(f"Health check: {response.status_code}")
        if response.status_code == 200:
            print(f"  Response: {response.json()}")
        print()
    except requests.exceptions.ConnectionError:
        print("Server not running. Please start the server first.")
        print("Run: uvicorn app:app --host 0.0.0.0 --port 8080")
        return

    # Test text embedding endpoint
    try:
        text_data = {"text": "A beautiful landscape with mountains"}
        response = requests.post(f"{base_url}/embed_query", json=text_data)
        print(f"Text embedding: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"  Embedding dimensions: {len(result['embedding'])}")
            print(f"  First 3 values: {result['embedding'][:3]}")
        else:
            print(f"  Error: {response.text}")
        print()
    except Exception as e:
        print(f"Error testing text embedding: {e}")
        print()

    # Test multiple texts endpoint
    try:
        texts_data = {
            "texts": [
                "A dog in the park",
                "A cat on the windowsill",
                "A bird in the sky",
            ]
        }
        response = requests.post(f"{base_url}/embed_documents", json=texts_data)
        print(f"Multiple texts embedding: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"  Number of embeddings: {len(result['embeddings'])}")
            print(f"  Embedding dimensions: {len(result['embeddings'][0])}")
        else:
            print(f"  Error: {response.text}")
        print()
    except Exception as e:
        print(f"Error testing multiple texts: {e}")
        print()


def curl_examples():
    """Example: Show curl commands for testing the API"""
    print("=" * 50)
    print("Curl Examples")
    print("=" * 50)

    print("1. Health Check:")
    print("   curl -X GET http://localhost:8080/health")
    print()

    print("2. Text Embedding:")
    print("   curl -X POST http://localhost:8080/embed_query \\")
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"text": "A beautiful sunset"}\'')
    print()

    print("3. Multiple Text Embeddings:")
    print("   curl -X POST http://localhost:8080/embed_documents \\")
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"texts": ["A dog", "A cat", "A bird"]}\'')
    print()

    print("4. Image Embedding from URL:")
    print("   curl -X POST http://localhost:8080/embed_image_url \\")
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"image_url": "https://example.com/image.jpg"}\'')
    print()


def environment_variable_examples():
    """Example: Show environment variable configurations"""
    print("=" * 50)
    print("Environment Variable Examples")
    print("=" * 50)

    print("1. Use CLIP model with CPU:")
    print("   export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16")
    print("   export EMBEDDING_USE_OV=false")
    print("   export EMBEDDING_DEVICE=CPU")
    print()

    print("2. Use MobileCLIP with OpenVINO:")
    print("   export EMBEDDING_MODEL_NAME=MobileCLIP/mobileclip_s0")
    print("   export EMBEDDING_USE_OV=true")
    print("   export EMBEDDING_DEVICE=CPU")
    print("   export EMBEDDING_OV_MODELS_DIR=./ov-models")
    print()

    print("3. Use SigLIP model:")
    print("   export EMBEDDING_MODEL_NAME=SigLIP/siglip2-vit-b-16")
    print("   export EMBEDDING_USE_OV=false")
    print("   export EMBEDDING_DEVICE=CPU")
    print()

    print("4. Use BLIP2 Transformers model:")
    print("   export EMBEDDING_MODEL_NAME=Blip2/blip2_transformers")
    print("   export EMBEDDING_USE_OV=false")
    print("   export EMBEDDING_DEVICE=CPU")
    print()

    print("5. Use BLIP2 Transformers with OpenVINO:")
    print("   export EMBEDDING_MODEL_NAME=Blip2/blip2_transformers")
    print("   export EMBEDDING_USE_OV=true")
    print("   export EMBEDDING_DEVICE=CPU")
    print("   export EMBEDDING_OV_MODELS_DIR=./ov-models")
    print()


def docker_examples():
    """Example: Show Docker usage"""
    print("=" * 50)
    print("Docker Examples")
    print("=" * 50)

    print("1. Build Docker image:")
    print("   docker build -t multimodal-embedding-serving .")
    print()

    print("2. Run with CLIP model:")
    print("   docker run -p 8080:8080 \\")
    print("     -e EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16 \\")
    print("     -e EMBEDDING_USE_OV=false \\")
    print("     multimodal-embedding-serving")
    print()

    print("3. Run with OpenVINO enabled:")
    print("   docker run -p 8080:8080 \\")
    print("     -e EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16 \\")
    print("     -e EMBEDDING_USE_OV=true \\")
    print("     -e EMBEDDING_DEVICE=CPU \\")
    print("     -v $(pwd)/ov-models:/app/ov-models \\")
    print("     multimodal-embedding-serving")
    print()

    print("4. Run with BLIP2 Transformers:")
    print("   docker run -p 8080:8080 \\")
    print("     -e EMBEDDING_MODEL_NAME=Blip2/blip2_transformers \\")
    print("     -e EMBEDDING_USE_OV=false \\")
    print("     -e EMBEDDING_DEVICE=CPU \\")
    print("     multimodal-embedding-serving")
    print()

    print("5. Run with BLIP2 Transformers + OpenVINO:")
    print("   docker run -p 8080:8080 \\")
    print("     -e EMBEDDING_MODEL_NAME=Blip2/blip2_transformers \\")
    print("     -e EMBEDDING_USE_OV=true \\")
    print("     -e EMBEDDING_DEVICE=CPU \\")
    print("     -v $(pwd)/ov-models:/app/ov-models \\")
    print("     multimodal-embedding-serving")
    print()


def main():
    """Run all server examples"""
    print("Multimodal Embedding Serving - Server Examples")
    print("=" * 70)
    print()

    # Server startup examples
    start_server_example()

    # Environment variable examples
    environment_variable_examples()

    # Curl examples
    curl_examples()

    # Docker examples
    docker_examples()

    # Test endpoints if server is running
    print("=" * 50)
    print("Testing Live Server (if running)")
    print("=" * 50)
    test_server_endpoints()

    print("=" * 70)
    print("Server examples completed!")


if __name__ == "__main__":
    main()
