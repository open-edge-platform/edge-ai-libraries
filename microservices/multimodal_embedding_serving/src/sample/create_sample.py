# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Sample data creation utilities for model testing and conversion.

This module provides utilities for creating sample data required for model
testing and OpenVINO conversion processes. It generates standard test images
with known properties that can be used for validation and conversion workflows.

The sample data ensures consistent testing environments and provides reliable
inputs for model conversion and validation processes.
"""

from PIL import Image
import os

def create_sample_image():
    """
    Create a sample image for OpenVINO model conversion and testing.
    
    Generates a simple 224x224 red RGB image that can be used as test input
    for model conversion processes, particularly OpenVINO conversion workflows.
    The image is saved to the same directory as this script.
    
    Returns:
        str: Path to the created sample image file
        
    Note:
        If the sample image already exists, the function returns the existing
        path without recreating the file, making it safe to call repeatedly.
    """
    sample_dir = os.path.dirname(__file__)
    os.makedirs(sample_dir, exist_ok=True)
    
    sample_image_path = os.path.join(sample_dir, "sample_image.jpg")
    
    if not os.path.exists(sample_image_path):
        # Create a simple red image
        image = Image.new('RGB', (224, 224), color='red')
        image.save(sample_image_path)
        print(f"Created sample image at {sample_image_path}")
    
    return sample_image_path

if __name__ == "__main__":
    create_sample_image()
