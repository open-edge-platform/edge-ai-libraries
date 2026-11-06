# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/visualization.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: functions that might be used for plots or image visualization
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt

# ------------------------------
# Visualization helper
# ------------------------------
def draw_boxes_on_pil(pil_img, crops, names=None, box_thickness=3, show_labels=True):
    draw = ImageDraw.Draw(pil_img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", size=18)
    except OSError:
        font = ImageFont.load_default()
    for crop in crops:

        # Use expanded_bbox if bbox is not available (e.g. on decoder side where bbox is not transmitted)
        bbox_coords = crop.bbox if crop.bbox is not None else crop.expanded_bbox
        x1, y1, x2, y2 = bbox_coords
        for t in range(box_thickness):
            draw.rectangle([x1-t, y1-t, x2+t, y2+t], outline="red")
        if show_labels:
            cls = crop.category_id
            label = f"{names[int(cls)] if (names and int(cls) in names) else int(cls)} {crop.det_conf:.2f}"
            bbox = draw.textbbox((0, 0), label, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            text_origin = (x1, max(0, y1 - text_h - 4))
            draw.rectangle([text_origin, (text_origin[0] + text_w + 4, text_origin[1] + text_h + 4)], fill="red")
            draw.text((text_origin[0] + 2, text_origin[1] + 2), label, fill="white", font=font)
    return pil_img


def save_composite_img(recon_with_boxes, name):
    try:
        recon_with_boxes.save(name)

    except (OSError, ValueError) as e:
        print("Visualization error (will continue):", repr(e))


def plot_gaussian_grid(k_values=(2, 5, 10, 20)):
    delta_f = np.linspace(0, 1, 500)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()

    for ax, k in zip(axes, k_values):
        similarity = np.exp(-k * delta_f**2)
        ax.plot(delta_f, similarity)
        ax.set_title(f"Gaussian (k={k})")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("Delta F1")
        ax.set_ylabel("Similarity")
        ax.grid(True)

    plt.tight_layout()
    plt.show()

def plot_logistic_grid(k_values=(2, 5, 10, 20), c=0.3):
    delta_f = np.linspace(0, 1, 500)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()

    for ax, k in zip(axes, k_values):
        similarity = 1.0 / (1.0 + np.exp(k * (delta_f - c)))
        ax.plot(delta_f, similarity)
        ax.set_title(f"Logistic (k={k}, c={c})")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("Delta F1")
        ax.set_ylabel("Similarity")
        ax.grid(True)

    plt.tight_layout()
    plt.show()

def plot_images(img1, img2, name):
    try:
        w = max(img1.width, img2.width)
        h = img1.height + img2.height

        combined = Image.new("RGB", (w, h))
        combined.paste(img1, (0, 0))
        combined.paste(img2, (0, img1.height))
        combined.save(name)

    except (OSError, ValueError) as e:
        print("Visualization error (will continue):", repr(e))


def save_enc_mask(mask, org_img_size, name):
    if mask is None:
        return
    elif isinstance(mask, tuple):
        num_masks = len(mask)
        if num_masks not in (2, 3):
            return  # silently skip if unexpected

        # Convert all masks to uint8 (0-255)
        masks_u8 = [np.asarray(m, dtype=np.uint8) * 255 for m in mask]

        # Resize each mask to target size
        masks_resized = [
            Image.fromarray(m_u8).resize(org_img_size, Image.Resampling.BICUBIC)
            for m_u8 in masks_u8
        ]

        # Create combined image side-by-side
        combined_width = org_img_size[0] * num_masks
        combined = Image.new("RGB", (combined_width, org_img_size[1]))
        for idx, m_resized in enumerate(masks_resized):
            combined.paste(m_resized, (org_img_size[0] * idx, 0))

        combined.save(name)
    else:
        mask_8bit = (mask == 1)
        # mask_2bit = ~mask_8bit
        # m2 = (mask_2bit.astype(np.uint8) * 255)
        m8 = (mask_8bit.astype(np.uint8) * 255)
        Image.fromarray(m8).resize(org_img_size, Image.Resampling.BICUBIC).save(name)
