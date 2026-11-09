# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/img_restorer.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: "optional" wrapper for using realESRGAN model to enhance the quality of decoded image.
"""

def enhance_image(pil_img, gpuid=-1, model=4):
    """
    pil_img: PIL Image to enhance
    gpuid: GPU id to use (-1 = CPU)
    model:
        0 = realESRGAN x2 model
        1 = x3 model
        2 = x4 model
        3 = realESRGAN-x4plus-anime
        4 = realESRGAN-x4plus (default)
    """

    from realesrgan_ncnn_py import Realesrgan

    # Prefer explicit GPU/CPU selection where supported by the installed binding.
    try:
        realesrgan = Realesrgan(model=model, gpuid=gpuid)
    except TypeError:
        realesrgan = Realesrgan(model=model)

    # Enhance image and return
    enhanced = realesrgan.process_pil(pil_img)
    return enhanced