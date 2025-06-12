# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import numpy as np
from PIL import Image
from pathlib import Path

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
