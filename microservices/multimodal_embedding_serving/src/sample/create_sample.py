# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Create a sample image for model conversion purposes.
"""

from PIL import Image
import os

def create_sample_image():
    """Create a sample image for OpenVINO model conversion."""
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
