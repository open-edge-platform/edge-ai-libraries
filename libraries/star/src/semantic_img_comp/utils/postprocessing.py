# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/postprocessing.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: functions that might be used post image de-compression
"""
from PIL import Image
import math
import numpy as np
from scipy.ndimage import distance_transform_edt


def _infer_margin_pixels(expanded_span: int, margin_percent: float) -> int:
    """Infer the per-side margin in pixels from an expanded crop span and configured margin percent.

    The denominator ``1 + 2*ratio`` reverses the symmetric expansion rule, because the expanded span equals the original span plus the margin on both sides: ``original * (1 + 2*ratio)``.
    """
    if expanded_span <= 0 or margin_percent <= 0:
        return 0

    ratio = margin_percent / 100.0
    return int(expanded_span * ratio / (1.0 + (2.0 * ratio)))


def paste_with_margin(
    img_dec_data,
    margin_percent=50,
    *,
    feather_ratio=0.5,
    feather_min_px=1,
):
    out = img_dec_data.bg.recon_pil.copy()

    # Ensure base is RGBA
    if out.mode != "RGBA":
        out = out.convert("RGBA")

    margin_percent = 0.0 if margin_percent is None else float(margin_percent)
    feather_ratio = float(feather_ratio)
    feather_min_px = int(feather_min_px)
    if not math.isfinite(feather_ratio) or feather_ratio < 0:
        raise ValueError(f"feather_ratio must be a finite non-negative number, got {feather_ratio!r}")
    if feather_min_px < 0:
        raise ValueError(f"feather_min_px must be >= 0, got {feather_min_px}")

    for crop in img_dec_data.crops:

        x1m, y1m, x2m, y2m = crop.expanded_bbox

        w_exp = x2m - x1m
        h_exp = y2m - y1m
        margin_pixel = max(
            _infer_margin_pixels(w_exp, margin_percent),
            _infer_margin_pixels(h_exp, margin_percent),
        )

        # Reconstruct interior offsets symmetrically from the configured crop-margin percent.
        # This is exact when at least one crop axis was not clipped at image boundaries.
        left_off = min(margin_pixel, w_exp // 2)
        top_off = min(margin_pixel, h_exp // 2)
        right_off = left_off
        bottom_off = top_off

        # --- Step 2: inward distance transform ---
        feather_width = max(int(margin_pixel * feather_ratio), feather_min_px) if margin_pixel > 0 else 0

        binary = np.zeros((h_exp, w_exp), dtype=np.uint8)
        binary[top_off : h_exp - bottom_off, left_off : w_exp - right_off] = 1

        dist_inside = distance_transform_edt(binary)

        # Protect center, feather only near boundary
        alpha = np.ones_like(dist_inside, dtype=np.float32)
        if feather_width > 0:
            edge_zone = dist_inside < feather_width
            alpha[edge_zone] = dist_inside[edge_zone] / feather_width

        final_mask = Image.fromarray((alpha * 255).astype(np.uint8), mode="L")

        # --- Step 4: alpha compositing (correct blending) ---

        # --- Expanded object canvas with transparency ---
        obj_exp = crop.recon_pil.convert("RGBA")  # already expanded, no shift needed

        # Ensure mask matches obj size
        final_mask_resized = final_mask.resize(obj_exp.size, resample=Image.Resampling.BICUBIC)
        if bool(getattr(crop, "sparse_overlay", False)):
            # Sparse line codecs carry black background + bright strokes. Convert stroke intensity
            # into alpha so only lines are composited onto the reconstructed background.
            line_luma = np.array(crop.recon_pil.convert("L"), dtype=np.uint8)
            margin_alpha = np.array(final_mask_resized, dtype=np.uint8)
            line_alpha = ((line_luma.astype(np.uint16) * margin_alpha.astype(np.uint16)) // 255).astype(np.uint8)
            rgba_arr = np.zeros((line_alpha.shape[0], line_alpha.shape[1], 4), dtype=np.uint8)
            rgba_arr[..., 0:3] = line_luma[..., None]
            rgba_arr[..., 3] = line_alpha
            obj_exp = Image.fromarray(rgba_arr, mode="RGBA")
        else:
            obj_exp.putalpha(final_mask_resized)

        # Composite directly into destination region; avoid allocating a full-frame layer per crop.
        try:
            out.alpha_composite(obj_exp, dest=(x1m, y1m))
        except TypeError:
            # Fallback for older Pillow versions that don't support the dest argument.
            layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
            layer.paste(obj_exp, (x1m, y1m))
            out = Image.alpha_composite(out, layer)

    out = out.convert("RGB")

    return out