# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import uuid
import numpy as np
from pathlib import Path
from PIL import Image
import base64
from io import BytesIO


def normalize(arr, mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]):
    arr = arr.astype(np.float32)
    arr /= 255.0
    for i in range(3):
        arr[...,i] = (arr[...,i] - mean[i]) / std[i]
    return arr

def preprocess_image(image, shape=[224,224]):
    img = image.resize(shape, Image.Resampling.NEAREST)
    img = normalize(np.asarray(img))
    return img.transpose(2,0,1)

def generate_unique_id():
    """
    Generate a random unique ID.

    Returns:
        A unique ID.
    """
    # return np.int64(uuid.uuid4().int & (1 << 64) - 1)
    return uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF

def encode_image_to_base64(image, format="PNG", add_header=False):
    """
    Encode an image to a base64 string.

    Args:
        image: PIL.Image.Image, path-like, or numpy ndarray (H,W,C in RGB).
        format: Output image format (e.g., "PNG", "JPEG").
        add_header: If True, prepend data URI header.

    Returns:
        Base64-encoded string (optionally with data URI header).
    """
    if isinstance(image, (str, Path)):
        img = Image.open(image).convert("RGB")
    elif isinstance(image, Image.Image):
        img = image.convert("RGB")
    elif isinstance(image, np.ndarray):
        if image.dtype != np.uint8:
            # Attempt to bring into 0-255 range if float
            if np.issubdtype(image.dtype, np.floating):
                arr = np.clip(image, 0, 1) if image.max() <= 1.0 else image
                image = (arr * (255 if arr.max() <= 1.0 else 1)).astype(np.uint8)
            else:
                image = image.astype(np.uint8)
        if image.ndim == 2:
            img = Image.fromarray(image, mode="L").convert("RGB")
        else:
            img = Image.fromarray(image[..., :3])
    else:
        raise TypeError("Unsupported image type for base64 encoding.")

    buffer = BytesIO()
    img.save(buffer, format=format)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    if add_header:
        return f"data:image/{format.lower()};base64,{encoded}"
    return encoded