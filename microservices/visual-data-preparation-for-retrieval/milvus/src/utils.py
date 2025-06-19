# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import uuid
import numpy as np
from pathlib import Path
from PIL import Image


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