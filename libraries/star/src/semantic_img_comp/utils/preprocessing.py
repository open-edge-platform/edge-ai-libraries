# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/preprocessing.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: functions that might be used prior to image compression
"""
from __future__ import annotations
import cv2
import numpy as np
from typing import Iterable, Tuple, Union, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# ------------------------------
# CROP BOXES
# ------------------------------
def crop_boxes_with_margin(pil_img, dets, margin_percent=50):
    """
    Returns:
      crops: list of PIL crops of the original boxes
      boxes: list of (x1,y1,x2,y2) original boxes
      expanded_boxes: list of (x1m,y1m,x2m,y2m) boxes expanded by margin
    """
    W, H = pil_img.size
    margin_percent = 0.0 if margin_percent is None else float(margin_percent)
    objs_pils, boxes, expanded_boxes = [], [], []

    for x1,y1,x2,y2,conf,cl in dets:
        x1 = int(max(0, x1)); y1 = int(max(0, y1))
        x2 = int(min(W, x2)); y2 = int(min(H, y2))
        if x2 <= x1 or y2 <= y1:
            continue

        margin_pixel = int(max((x2 - x1), (y2 - y1)) * margin_percent / 100)

        # Expand the box by margin
        x1m = int(max(0, x1 - margin_pixel))
        y1m = int(max(0, y1 - margin_pixel))
        x2m = int(min(W, x2 + margin_pixel))
        y2m = int(min(H, y2 + margin_pixel))

        objs_pils.append(pil_img.crop((x1m, y1m, x2m, y2m)))
        boxes.append((x1,y1,x2,y2))
        expanded_boxes.append((x1m, y1m, x2m, y2m))

    return objs_pils, boxes, expanded_boxes

# ------------------------------
# RESIZE WITH PADDING
# ------------------------------
def resize_with_padding(pil_img, target_size):
    """
    Resize image to target_size while preserving aspect ratio.
    Returns:
      resized_padded_img, scale, pad (left, top)
    """
    W, H = pil_img.size
    tw, th = target_size

    scale = min(tw / W, th / H)
    nw, nh = int(W * scale), int(H * scale)

    img_resized = pil_img.resize((nw, nh), Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))

    pad_x = (tw - nw) // 2
    pad_y = (th - nh) // 2
    canvas.paste(img_resized, (pad_x, pad_y))

    return canvas, scale, (pad_x, pad_y)

def downsize_img(img: Image.Image, scale_percent: int =100, resample=Image.Resampling.BICUBIC) -> Image.Image:

    img = img.resize(
        (int(img.width * scale_percent / 100), int(img.height * scale_percent / 100)),
        resample=resample,
    )

    return img

# ------------------------------
# CARVE OUT DET OBJ FROM BG
# ------------------------------
BBox = Tuple[float, float, float, float]


def bboxes_to_mask(size: tuple[int, int], bboxes: Iterable[BBox], *, fill: int = 255) -> Image.Image:
    """Build an L-mode mask where bbox interiors are set to *fill* and elsewhere is 0."""
    w, h = size
    if w <= 0 or h <= 0:
        raise ValueError(f"size must be positive, got {size!r}")

    fill_val = int(fill)
    if fill_val < 0 or fill_val > 255:
        raise ValueError(f"fill must be in range [0, 255], got {fill!r}")

    out = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(out)
    for bbox in bboxes:
        x1, y1, x2, y2 = bbox
        x1, x2 = sorted((int(round(x1)), int(round(x2))))
        y1, y2 = sorted((int(round(y1)), int(round(y2))))
        x1 = max(0, min(w, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        draw.rectangle([x1, y1, x2, y2], fill=fill_val)
    return out


def clear_bboxes_in_mask(mask: Image.Image, bboxes: Iterable[BBox], *, fill: int = 0) -> Image.Image:
    """Return a copy of *mask* with the provided bbox regions filled to a constant value."""
    if mask is None:
        raise ValueError("mask must not be None")

    out = mask.convert("L").copy()
    w, h = out.size
    draw = ImageDraw.Draw(out)

    fill_val = int(fill)
    if fill_val < 0 or fill_val > 255:
        raise ValueError(f"fill must be in range [0, 255], got {fill!r}")

    for bbox in bboxes:
        x1, y1, x2, y2 = bbox
        x1, x2 = sorted((int(round(x1)), int(round(x2))))
        y1, y2 = sorted((int(round(y1)), int(round(y2))))
        x1 = max(0, min(w, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        draw.rectangle([x1, y1, x2, y2], fill=fill_val)

    return out


def del_obj_from_bg(
    img: Image.Image,
    bbox: BBox,
    *,
    feather_px: int = 8,
    blur_radius: Optional[float] = None,
    fill: Union[int, Tuple[int, int, int]] = (0, 0, 0),
) -> Image.Image:
    """
    Black out a bbox region and feather the transition *inward only*:
    - Pixels outside the bbox are unchanged.
    - Pixels inside become black, but near the bbox edge they blend smoothly
      from original -> black over ~feather_px pixels.

    Args:
        img: Input PIL image.
        bbox: (x1, y1, x2, y2) in pixel coords (floats ok).
        feather_px: Width of the inward feather band in pixels. 0 => hard edge.
        blur_radius: Gaussian blur radius controlling smoothness. If None and
                     feather_px>0, uses max(1, feather_px/2).
        fill: Fill color (black). For RGB use (0,0,0). For L use 0.

    Returns:
        New PIL image.
    """
    base = img.convert("RGB") if img.mode not in ("RGB", "RGBA", "L") else img.copy()
    w, h = base.size

    x1, y1, x2, y2 = bbox
    x1, x2 = sorted((int(round(x1)), int(round(x2))))
    y1, y2 = sorted((int(round(y1)), int(round(y2))))
    x1 = max(0, min(w, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h, y1))
    y2 = max(0, min(h, y2))

    if x2 <= x1 or y2 <= y1:
        return base

    # Hard mask for "inside bbox"
    hard = Image.new("L", (w, h), 0)
    ImageDraw.Draw(hard).rectangle([x1, y1, x2, y2], fill=255)

    if not feather_px or feather_px <= 0:
        mask = hard
    else:
        if blur_radius is None:
            blur_radius = max(1.0, feather_px / 2.0)

        # Create a slightly *shrunk* inner rectangle; blur it, then clamp to bbox.
        # This produces a gradient that ramps up to 255 as you go inward, while
        # remaining 0 outside the bbox (inward-only feather).
        inset = max(0, int(feather_px))
        xi1, yi1 = x1 + inset, y1 + inset
        xi2, yi2 = x2 - inset, y2 - inset

        inner = Image.new("L", (w, h), 0)
        if xi2 > xi1 and yi2 > yi1:
            ImageDraw.Draw(inner).rectangle([xi1, yi1, xi2, yi2], fill=255)
        else:
            # bbox is too small; just use hard mask
            inner = hard.copy()

        soft = inner.filter(ImageFilter.GaussianBlur(radius=float(blur_radius)))

        # Ensure we never affect outside bbox:
        # mask = min(soft, hard)  (since hard is 0 outside bbox)
        mask = ImageChops.multiply(soft, hard)
        # multiply scales 0..255; inside bbox it keeps soft, outside becomes 0.

    fill_img = Image.new(base.mode, (w, h), fill)
    out = Image.composite(fill_img, base, mask)
    return out

# ------------------------------
# EDGE DETECTION
# ------------------------------
def canny_edge_det(img: Image.Image, *, canny_sigma: float = 1.0, canny_low: int = 50, canny_high: int = 150):
    """Canny-based edge mask used by mixed-bit encoders."""
    img = img.convert("L")
    w, h = img.size
    img_np = np.array(img, dtype=np.uint8)

    if canny_sigma and canny_sigma > 0:
        img_for_canny = cv2.GaussianBlur(img_np, (0, 0), float(canny_sigma))
    else:
        img_for_canny = img_np

    edges = cv2.Canny(img_for_canny, threshold1=canny_low, threshold2=canny_high)
    edge = (edges > 0).astype(np.uint8)

    kernel3 = np.ones((3, 3), np.uint8)
    edge = cv2.dilate(edge, kernel3).astype(np.uint8)

    mask = (edge == 1).astype(np.uint8).flatten().reshape((h, w))
    return Image.fromarray((mask * 255).astype(np.uint8))


def canny_deriche_edge_det(
    img: Image.Image,
    *,
    canny_low: int = 15,
    canny_high: int = 60,
    bilateral_d: int = 9,
    bilateral_sigma_color: float = 60,
    bilateral_sigma_space: float = 60,
    gaussian_sigma: float = 1.8,
    morph_close_kernel: int = 7,
    morph_close_iterations: int = 2,
):
    """Canny edge mask with bilateral+gaussian smoothing and optional morphological closing."""
    gray = img.convert("L")
    gray_np = np.array(gray, dtype=np.uint8)
    h, w = gray_np.shape

    denoised = cv2.bilateralFilter(
        gray_np,
        int(bilateral_d),
        float(bilateral_sigma_color),
        float(bilateral_sigma_space),
    )
    smoothed = cv2.GaussianBlur(denoised, (0, 0), float(gaussian_sigma))
    edges = cv2.Canny(smoothed, threshold1=int(canny_low), threshold2=int(canny_high))

    k = int(morph_close_kernel)
    if k > 1:
        edges = cv2.morphologyEx(
            edges,
            cv2.MORPH_CLOSE,
            np.ones((k, k), np.uint8),
            iterations=int(morph_close_iterations),
        )

    mask = (edges > 0).astype(np.uint8).flatten().reshape((h, w))
    return Image.fromarray((mask * 255).astype(np.uint8))


def select_canny_edge_det(
    img: Image.Image,
    *,
    mode: str = "old",
    canny_sigma: float = 1.0,
    canny_low: int = 15,
    canny_high: int = 60,
    canny_deriche_bilateral_d: int = 9,
    canny_deriche_bilateral_sigma_color: float = 60,
    canny_deriche_bilateral_sigma_space: float = 60,
    canny_deriche_gaussian_sigma: float = 1.8,
    canny_deriche_morph_close_kernel: int = 7,
    canny_deriche_morph_close_iterations: int = 2,
) -> Image.Image:
    """Select legacy or canny-deriche preprocessing based on config mode."""
    normalized = str(mode).strip().lower()
    if normalized in {"old", "legacy", "canny"}:
        return canny_edge_det(
            img,
            canny_sigma=float(canny_sigma),
            canny_low=int(canny_low),
            canny_high=int(canny_high),
        )
    if normalized in {"new", "canny_deriche", "deriche"}:
        return canny_deriche_edge_det(
            img,
            canny_low=int(canny_low),
            canny_high=int(canny_high),
            bilateral_d=int(canny_deriche_bilateral_d),
            bilateral_sigma_color=float(canny_deriche_bilateral_sigma_color),
            bilateral_sigma_space=float(canny_deriche_bilateral_sigma_space),
            gaussian_sigma=float(canny_deriche_gaussian_sigma),
            morph_close_kernel=int(canny_deriche_morph_close_kernel),
            morph_close_iterations=int(canny_deriche_morph_close_iterations),
        )

    raise ValueError(
        f"Unsupported canny mode: {mode!r}. Expected one of: old, new"
    )
