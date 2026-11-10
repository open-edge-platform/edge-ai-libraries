# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: encoder/codecs.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: Low-level encoder codec implementations.
"""

from pathlib import Path
from typing import Optional
import subprocess  # nosec B404 - used only to invoke the fixed 'avifenc' binary with an argv list, no shell
import tempfile
import zlib

import cv2
import numpy as np
from PIL import Image


# ---------------------------------
# AVIF
# ---------------------------------
def encode_avif(
    img: Image.Image,
    quality: int = 50,
    speed: int = 6,
    is_monochrome: bool = False,
    timeout_sec: Optional[int] = None,
    jobs: Optional[int] = None,
    codec: Optional[str] = None,
) -> bytes:
    """Encode image to AVIF bitstream using the external ``avifenc`` tool.

    If is_monochrome=True: encodes as 1-channel YUV400 (grayscale).
    If is_monochrome=False: encodes as 3-channel YUV420 (color RGB).
    """
    if timeout_sec is None:
        timeout_sec = 120  # fallback if not provided via config
    # choose pixel format
    if is_monochrome:
        yuv = "400"
        img = img.convert("L")
    else:
        yuv = "420"
        img = img.convert("RGB")

    with tempfile.TemporaryDirectory(prefix="semantic_img_comp_avif_") as temp_dir:
        temp_dir_path = Path(temp_dir)
        png_in = temp_dir_path / "input.png"
        avif_out = temp_dir_path / "output.avif"

        # Write the temporary PNG first. TemporaryDirectory avoids the file
        # handle locking issues that NamedTemporaryFile can trigger on Windows.
        img.save(png_in, format="PNG")

        if codec == "svt" and is_monochrome:
            print("SVT-AV1 cannot encode YUV400; falling back to default.")
            codec = None

        if codec == "svt":
            codec_arg = ["-q", "100"]
        else:
            codec_arg = [
                "--min", str(quality),
                "--max", str(quality)
            ]

        cmd = [
            "avifenc",
            *codec_arg,
            "--speed", str(speed),
            "--yuv", yuv,
        ]

        if jobs is not None and jobs > 0:
            cmd.extend(["--jobs", str(jobs)])
        if codec:
            cmd.extend(["--codec", str(codec)])

        cmd.extend([str(png_in), str(avif_out)])

        try:
            # Fixed executable name, argv list (no shell=True); paths are generated
            # by this function's own TemporaryDirectory, not attacker-controlled.
            subprocess.run(  # nosec B603
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_sec,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                "The 'avifenc' executable was not found on PATH. "
                "Install libavif tools or make avifenc available before using AVIF encoders."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("avifenc timed out while encoding an image") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(
                f"avifenc failed with exit code {exc.returncode}: {stderr or 'no stderr output'}"
            ) from exc

        return avif_out.read_bytes()

# ---------------------------------
# 2-bit encoding
# ---------------------------------
def encode_color_2bit(img: Image.Image, zlib_level: int = 9) -> bytes:
    arr = np.array(img, dtype=np.uint8)  # (h,w,3)

    # 2-bit quantization
    arr2 = (arr // 64).astype(np.uint8)

    flat = arr2.reshape(-1, 3)
    total_pixels = flat.shape[0]

    pad = (-total_pixels) % 4
    if pad:
        flat = np.vstack([flat, np.zeros((pad, 3), dtype=np.uint8)])

    packed_channels = []

    for c in range(3):
        ch = flat[:, c]
        packed = (
            (ch[0::4] << 6) |
            (ch[1::4] << 4) |
            (ch[2::4] << 2) |
            (ch[3::4])
        ).astype(np.uint8)

        packed_channels.append(packed)

    packed_all = np.concatenate(packed_channels)
    compressed = zlib.compress(packed_all.tobytes(), level=zlib_level)

    return compressed


def encode_mono_2bit(img: Image.Image, zlib_level: int = 9, *, skip_mask: Optional[Image.Image] = None) -> bytes:
    """Encode grayscale image into 2-bit packed stream + zlib."""
    img = img.convert("L")
    arr = np.array(img, dtype=np.uint8)

    # 0..255 -> 0..3
    q = (arr // 64).astype(np.uint8)

    flat = q.flatten()

    if skip_mask is not None:
        skip_arr = (np.array(skip_mask.convert("L"), dtype=np.uint8) > 0).flatten()
        if skip_arr.size != flat.size:
            raise ValueError(
                f"skip_mask size mismatch: expected {flat.size} pixels for image size {img.size}, got {skip_arr.size}"
            )

        keep = (skip_arr == 0)
        vals = flat[keep]
        pad = (-vals.size) % 4
        if pad:
            vals = np.concatenate([vals, np.zeros(pad, dtype=np.uint8)])

        packed = (
            (vals[0::4] << 6)
            | (vals[1::4] << 4)
            | (vals[2::4] << 2)
            | (vals[3::4])
        ).astype(np.uint8)

        # Sparse mono-2bit payload marker (0xFF), then pad count, then packed kept pixels.
        payload = np.array([255, pad], dtype=np.uint8).tobytes() + packed.tobytes()
        return zlib.compress(payload, level=zlib_level)

    total_pixels = flat.size

    # pad stream to 4-value boundary (4 pixels per output byte)
    pad = (-total_pixels) % 4
    if pad:
        flat = np.concatenate([flat, np.zeros(pad, dtype=np.uint8)])

    packed = (
        (flat[0::4] << 6) |
        (flat[1::4] << 4) |
        (flat[2::4] << 2) |
        (flat[3::4])
    ).astype(np.uint8)

    return zlib.compress(packed.tobytes(), level=zlib_level)

def encode_mono_2bit_mixed_n1bit(
    img: Image.Image,
    zlib_level: int = 9,
    *,
    two_bit_run: int = 4,
    one_bit_run: int = 1,
    skip_mask: Optional[Image.Image] = None,
) -> bytes:
    """Encode grayscale with a fixed template: N pixels at 2-bit then M at 1-bit."""
    if two_bit_run <= 0:
        raise ValueError(f"two_bit_run must be > 0, got {two_bit_run}")
    if one_bit_run <= 0:
        raise ValueError(f"one_bit_run must be > 0, got {one_bit_run}")

    img = img.convert("L")
    arr = np.array(img, dtype=np.uint8)
    flat = (arr // 64).astype(np.uint8).flatten()

    if skip_mask is not None:
        skip_arr = (np.array(skip_mask.convert("L"), dtype=np.uint8) > 0).flatten()
        if skip_arr.size != flat.size:
            raise ValueError(
                f"skip_mask size mismatch: expected {flat.size} pixels for image size {img.size}, got {skip_arr.size}"
            )
        flat = flat[skip_arr == 0]

    cycle = int(two_bit_run + one_bit_run)
    idx = np.arange(flat.size, dtype=np.int64)
    two_bit_sel = (idx % cycle) < int(two_bit_run)

    vals_2 = flat[two_bit_sel]
    vals_1 = (flat[~two_bit_sel] >= 2).astype(np.uint8)

    packed_2, pad_2 = _pack_bits(vals_2, 2)
    packed_1, pad_1 = _pack_bits(vals_1, 1)

    if skip_mask is None:
        payload = np.array([pad_2, pad_1], dtype=np.uint8).tobytes() + packed_2 + packed_1
    else:
        # Sparse payload marker (0xFF), then both pad counts, then packed streams.
        payload = np.array([255, pad_2, pad_1], dtype=np.uint8).tobytes() + packed_2 + packed_1

    return zlib.compress(payload, level=zlib_level)


def encode_mono_2bit_template_drop1bit(
    img: Image.Image,
    zlib_level: int = 9,
    *,
    two_bit_run: int = 4,
    one_bit_run: int = 1,
    skip_mask: Optional[Image.Image] = None,
) -> bytes:
    """Encode by area-downsampling to ratio n/(n+m) height then 2-bit packing.

    Decoder recovers full resolution via bicubic upsampling.
    skip_mask pixels are zeroed before downsampling so those regions encode as black
    (they will be overwritten by object crops at the compositing stage).
    """
    if two_bit_run <= 0:
        raise ValueError(f"two_bit_run must be > 0, got {two_bit_run}")
    if one_bit_run <= 0:
        raise ValueError(f"one_bit_run must be > 0, got {one_bit_run}")

    img = img.convert("L")

    if skip_mask is not None:
        skip_arr = (np.array(skip_mask.convert("L"), dtype=np.uint8) > 0)
        if skip_arr.shape != (img.height, img.width):
            raise ValueError(
                f"skip_mask size mismatch: expected {(img.width, img.height)}, got {skip_mask.size}"
            )
        arr = np.array(img, dtype=np.uint8)
        arr[skip_arr] = 0
        img = Image.fromarray(arr, mode="L")

    ratio = float(two_bit_run) / float(two_bit_run + one_bit_run)
    new_h = max(1, int(round(img.height * ratio)))
    img_sub = img.resize((img.width, new_h), Image.Resampling.BOX)

    flat = (np.array(img_sub, dtype=np.uint8) // 64).astype(np.uint8).flatten()
    packed, pad = _pack_bits(flat, 2)

    payload = np.array([pad], dtype=np.uint8).tobytes() + packed
    return zlib.compress(payload, level=zlib_level)

# ---------------------------------
# 4-bit encoding
# ---------------------------------
def encode_color_4bit(img: Image.Image, zlib_level: int = 9) -> bytes:
    arr = np.array(img, dtype=np.uint8)

    # quantize
    q = (arr // 16).astype(np.uint8)

    flat = q.reshape(-1)
    total_vals = flat.size  # values, not pixels

    # need even number of values
    pad = (-total_vals) % 2
    if pad:
        flat = np.concatenate([flat, np.zeros(pad, dtype=np.uint8)])

    packed = (
        (flat[0::2] << 4) |
        (flat[1::2])
    ).astype(np.uint8)

    return zlib.compress(packed.tobytes(), level=zlib_level)


def encode_mono_4bit(img: Image.Image, zlib_level: int = 9) -> bytes:
    img = img.convert("L")
    arr = np.array(img, dtype=np.uint8)

    # 0..255 -> 0..15
    q = (arr // 16).astype(np.uint8)

    flat = q.flatten()
    total_pixels = flat.size

    # pad stream to even number of pixels (2 pixels per byte)
    pad = (-total_pixels) % 2
    if pad:
        flat = np.concatenate([flat, np.zeros(pad, dtype=np.uint8)])

    packed = (
        (flat[0::2] << 4) |
        (flat[1::2])
    ).astype(np.uint8)

    return zlib.compress(packed.tobytes(), level=zlib_level)

# ---------------------------------
# 8-bit encoding
# ---------------------------------
def encode_color_8bit(img: Image.Image, zlib_level: int = 9) -> bytes:
    img = img.convert("RGB")
    arr = np.array(img, dtype=np.uint8)
    raw = arr.tobytes()
    return zlib.compress(raw, level=zlib_level)


def encode_mono_8bit(img: Image.Image, zlib_level: int = 9) -> bytes:
    """No quantization: grayscale + zlib."""
    img = img.convert("L")
    arr = np.array(img, dtype=np.uint8)
    raw = arr.tobytes()
    return zlib.compress(raw, level=zlib_level)

# ---------------------------------
# 2/8-bit encoding
# ---------------------------------
def encode_color_28bit(img: Image.Image, mask=None, zlib_level: int = 9) -> bytes:
    """RGB 2/8-bit encoder with shared 1-bit mask over pixels."""
    img = img.convert("RGB")
    img_np = np.array(img, dtype=np.uint8)
    pixels = img_np.reshape(-1, 3)

    if mask is None:
        raise ValueError("mask is required for encode_rgb_28bit (same as your mono path).")
    mask_8 = (np.array(mask) > 0).astype(np.uint8).flatten()

    mask_8_packed, mask_8_pad = _pack_bits(mask_8, 1)

    vals_8 = pixels[mask_8 == 1]
    vals_2 = pixels[mask_8 == 0]

    q2 = ((vals_2.astype(np.uint16) * 4) // 256).astype(np.uint8)
    q2_flat = q2.reshape(-1)
    q2_packed, q2_pad = _pack_bits(q2_flat, 2)

    header = np.array([mask_8_pad, q2_pad], dtype=np.uint8).tobytes()
    header += np.array([vals_8.shape[0]], dtype=np.uint32).tobytes()

    payload = header + mask_8_packed + vals_8.tobytes() + q2_packed
    return zlib.compress(payload, level=zlib_level)

def encode_mono_28bit(img: Image.Image, mask=None, zlib_level: int = 9) -> bytes:
    img = img.convert("L")
    img_np = np.array(img, dtype=np.uint8)
    pixels = img_np.flatten()

    mask_8 = (np.array(mask) > 0).astype(np.uint8).flatten()
    mask_8_packed, mask_8_pad = _pack_bits(mask_8, 1)

    vals_8 = pixels[mask_8 == 1]
    vals_2 = pixels[mask_8 == 0]

    q2 = ((vals_2.astype(np.uint16) * 4) // 256).astype(np.uint8)
    q2_packed, q2_pad = _pack_bits(q2, 2)

    header = np.array([mask_8_pad, q2_pad], dtype=np.uint8).tobytes()
    header += np.array([vals_8.size], dtype=np.uint32).tobytes()

    payload = header + mask_8_packed + vals_8.tobytes() + q2_packed
    return zlib.compress(payload, level=zlib_level)

# ---------------------------------
# 1/8-bit encoding [mono only]
# ---------------------------------
def encode_mono_18bit(img: Image.Image, mask=None, zlib_level: int = 9) -> bytes:
    """1/8-bit encoder: mask==1 raw 8-bit, mask==0 thresholded 1-bit."""
    img = img.convert("L")
    img_np = np.array(img, dtype=np.uint8)
    pixels = img_np.flatten()

    if mask is None:
        raise ValueError("mask is required")

    mask_8 = (np.array(mask) > 0).astype(np.uint8).flatten()
    mask_8_packed, mask_8_pad = _pack_bits(mask_8, 1)

    vals_8 = pixels[mask_8 == 1]
    vals_1 = pixels[mask_8 == 0]

    q1 = (vals_1 >= 128).astype(np.uint8)
    q1_packed, q1_pad = _pack_bits(q1, 1)

    header = np.array([mask_8_pad, q1_pad], dtype=np.uint8).tobytes()
    header += np.array([vals_8.size], dtype=np.uint32).tobytes()

    payload = header + mask_8_packed + vals_8.tobytes() + q1_packed
    return zlib.compress(payload, level=zlib_level)

# ---------------------------------
# 1-bit encoding of edge mask only
# ---------------------------------
def encode_mono_mask_1bit(
    img: Image.Image,
    mask=None,
    zlib_level: int = 9,
    *,
    skip_mask: Optional[Image.Image] = None,
) -> bytes:
    """Mask-only encoder: transmit only the binary mask as a packed 1-bit stream."""
    if mask is None:
        raise ValueError("mask is required")

    expected_pixels = img.width * img.height
    mask_1bit = (np.array(mask) > 0).astype(np.uint8)
    if mask_1bit.size != expected_pixels:
        raise ValueError(
            f"mask size mismatch: expected {expected_pixels} pixels for image size {img.size}, got {mask_1bit.size}"
        )

    flat = mask_1bit.flatten()
    if skip_mask is not None:
        skip_arr = (np.array(skip_mask.convert("L"), dtype=np.uint8) > 0).flatten()
        if skip_arr.size != flat.size:
            raise ValueError(
                f"skip_mask size mismatch: expected {flat.size} pixels for image size {img.size}, got {skip_arr.size}"
            )
        flat = flat[skip_arr == 0]

    mask_packed, mask_pad = _pack_bits(flat, 1)
    if skip_mask is None:
        payload = np.array([mask_pad], dtype=np.uint8).tobytes() + mask_packed
    else:
        payload = np.array([255, mask_pad], dtype=np.uint8).tobytes() + mask_packed
    return zlib.compress(payload, level=zlib_level)


# ---------------------------------
# Skeleton primitive encoding [mono only]
# ---------------------------------
def encode_mono_skel_v1(
    img: Image.Image,
    zlib_level: int = 9,
    *,
    max_segments: int = 8,
    min_segment_length: int = 5,
    hough_threshold: int = 20,
    max_segment_gap: int = 2,
    work_max_dim: int = 128,
    stitch_angle_tol_deg: float = 20.0,
) -> bytes:
    """Encode image as sparse skeleton segments without Canny/edge detection.

    Pipeline (bounded for predictable runtime):
    1. Downscale to 128px max dim (working size).
    2. Otsu threshold + polarity selection.
    3. Morphological close (bridge small gaps).
    4. Morphological skeleton with HARD 30-iteration cap.
    5. HoughLinesP on skeleton → top-K longest segments.
    6. Quantize coords back to original image space [0,255].

    Payload layout before zlib:
    - uint8: format version (1)
    - uint8: segment count N
    - N * (uint8 x1, uint8 y1, uint8 x2, uint8 y2)
    """
    if max_segments <= 0:
        raise ValueError(f"max_segments must be > 0, got {max_segments}")

    orig_w, orig_h = img.width, img.height
    # Configurable detail knob; clamp to keep runtime bounded.
    WORK_MAX = int(np.clip(int(work_max_dim), 64, 512))

    gray = np.array(img.convert("L"), dtype=np.uint8)
    if max(orig_h, orig_w) > WORK_MAX:
        s = float(WORK_MAX) / float(max(orig_h, orig_w))
        ww = max(2, int(round(orig_w * s)))
        wh = max(2, int(round(orig_h * s)))
        gray = cv2.resize(gray, (ww, wh), interpolation=cv2.INTER_AREA)
    h, w = gray.shape

    def _q(c: int, maxc: int) -> int:
        return int(np.clip(round(c * 255.0 / max(1, maxc)), 0, 255))

    def _scale_seg(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
        ox1 = int(np.clip(round(x1 * orig_w / max(1, w)), 0, orig_w - 1))
        oy1 = int(np.clip(round(y1 * orig_h / max(1, h)), 0, orig_h - 1))
        ox2 = int(np.clip(round(x2 * orig_w / max(1, w)), 0, orig_w - 1))
        oy2 = int(np.clip(round(y2 * orig_h / max(1, h)), 0, orig_h - 1))
        return (_q(ox1, orig_w - 1), _q(oy1, orig_h - 1), _q(ox2, orig_w - 1), _q(oy2, orig_h - 1))

    if h <= 1 or w <= 1:
        return zlib.compress(bytes((1, 0)), level=zlib_level)

    # Otsu threshold; keep polarity with ≤ 50% foreground to avoid full-image blobs.
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cv2.countNonZero(bw) > bw.size // 2:
        bw = cv2.bitwise_not(bw)

    # Morphological close to bridge small gaps in object structure.
    gap = min(4, max(0, int(max_segment_gap)))
    if gap > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * gap + 1, 2 * gap + 1))
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, k, iterations=1)

    # Skeletonization — HARD 30-iteration cap prevents stalls on dense masks.
    if hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "thinning"):
        skel = cv2.ximgproc.thinning(bw)
    else:
        skel = np.zeros_like(bw)
        work = bw.copy()
        cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        for _ in range(30):  # HARD CAP — was unbounded before, causing pipeline stalls
            if cv2.countNonZero(work) == 0:
                break
            opened = cv2.morphologyEx(work, cv2.MORPH_OPEN, cross)
            skel = cv2.bitwise_or(skel, cv2.subtract(work, opened))
            work = cv2.erode(work, cross)

    line_source = skel if cv2.countNonZero(skel) > 0 else bw

    # Extract line segments directly — no graph traversal.
    lines = cv2.HoughLinesP(
        line_source,
        rho=1,
        theta=np.pi / 180.0,
        threshold=max(1, int(hough_threshold)),
        minLineLength=max(1, int(min_segment_length)),
        maxLineGap=gap,
    )

    scored: list[tuple[float, int, int, int, int]] = []
    if lines is not None and len(lines) > 0:
        for seg in lines.reshape(-1, 4):
            x1, y1, x2, y2 = int(seg[0]), int(seg[1]), int(seg[2]), int(seg[3])
            length = float(np.hypot(x2 - x1, y2 - y1))
            if length >= float(max(1, int(min_segment_length))):
                scored.append((length, x1, y1, x2, y2))

    # Keep a bounded candidate set, then stitch nearby collinear segments to improve
    # object continuity (reduces disconnected short fragments).
    scored.sort(reverse=True, key=lambda t: t[0])
    candidate_cap = max(64, int(max_segments) * 6)
    scored = scored[:candidate_cap]

    def _seg_angle_deg(x1: int, y1: int, x2: int, y2: int) -> float:
        return float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))

    def _angle_diff_deg(a: float, b: float) -> float:
        # Undirected segment orientation: 0 and 180 are equivalent.
        d = abs(a - b) % 180.0
        return min(d, 180.0 - d)

    def _endpoint_min_dist(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        pairs = [
            (ax1, ay1, bx1, by1),
            (ax1, ay1, bx2, by2),
            (ax2, ay2, bx1, by1),
            (ax2, ay2, bx2, by2),
        ]
        return min(float(np.hypot(px - qx, py - qy)) for px, py, qx, qy in pairs)

    def _merge_to_farthest_pair(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        pts = [(a[0], a[1]), (a[2], a[3]), (b[0], b[1]), (b[2], b[3])]
        best = (pts[0], pts[1])
        best_d = -1.0
        for i in range(4):
            for j in range(i + 1, 4):
                d = float(np.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
                if d > best_d:
                    best_d = d
                    best = (pts[i], pts[j])
        return (best[0][0], best[0][1], best[1][0], best[1][1])

    stitch_gap_px = float(max(2, int(max_segment_gap) * 2 + 2))
    stitch_angle_tol_deg = float(np.clip(float(stitch_angle_tol_deg), 1.0, 89.0))
    segs = [(x1, y1, x2, y2) for _, x1, y1, x2, y2 in scored]

    # Bounded O(N^2) greedy stitching.
    changed = True
    iters = 0
    max_iters = 40
    while changed and iters < max_iters and len(segs) > 1:
        iters += 1
        changed = False
        used = [False] * len(segs)
        merged_out: list[tuple[int, int, int, int]] = []

        for i in range(len(segs)):
            if used[i]:
                continue
            cur = segs[i]
            cur_ang = _seg_angle_deg(*cur)
            for j in range(i + 1, len(segs)):
                if used[j]:
                    continue
                other = segs[j]
                other_ang = _seg_angle_deg(*other)
                if _angle_diff_deg(cur_ang, other_ang) > stitch_angle_tol_deg:
                    continue
                if _endpoint_min_dist(cur, other) > stitch_gap_px:
                    continue
                cur = _merge_to_farthest_pair(cur, other)
                cur_ang = _seg_angle_deg(*cur)
                used[j] = True
                changed = True
            used[i] = True
            merged_out.append(cur)

        # Keep bounded candidate count between iterations.
        if len(merged_out) > candidate_cap:
            merged_out = sorted(
                merged_out,
                key=lambda s: float(np.hypot(s[2] - s[0], s[3] - s[1])),
                reverse=True,
            )[:candidate_cap]
        segs = merged_out

    scored = [
        (float(np.hypot(x2 - x1, y2 - y1)), x1, y1, x2, y2)
        for x1, y1, x2, y2 in segs
        if float(np.hypot(x2 - x1, y2 - y1)) >= float(max(1, int(min_segment_length)))
    ]
    scored.sort(reverse=True, key=lambda t: t[0])

    packed: list[tuple[int, int, int, int]] = []
    for _, x1, y1, x2, y2 in scored[:max_segments]:
        packed.append(_scale_seg(x1, y1, x2, y2))

    # Bounding-box fallback when no segments survive.
    if not packed:
        ys, xs = np.where(line_source > 0)
        if xs.size >= 2:
            packed.append(_scale_seg(int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))

    n = min(len(packed), 255)
    header = bytes((1, n))
    body = b"".join(bytes(s) for s in packed[:n])
    return zlib.compress(header + body, level=zlib_level)


def _estimate_major_axis_theta_deg(img: Image.Image) -> float:
    """Estimate object orientation (0..180 deg) from the dominant contour axis.

    Returns 0.0 when the crop has insufficient foreground structure.
    """
    arr = np.array(img.convert("L"), dtype=np.uint8)
    if arr.size == 0:
        return 0.0

    _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cv2.countNonZero(bw) > bw.size // 2:
        bw = cv2.bitwise_not(bw)

    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return 0.0

    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 4.0:
        return 0.0

    (center, wh, angle) = cv2.minAreaRect(contour)
    _ = center
    w_rect, h_rect = float(wh[0]), float(wh[1])
    theta = float(angle)
    # OpenCV minAreaRect angle is in [-90, 0). Adjust to the major axis.
    if w_rect < h_rect:
        theta += 90.0
    theta = theta % 180.0
    return theta


def _extract_primary_contour_points(img: Image.Image, *, min_area: float) -> Optional[np.ndarray]:
    """Extract the dominant contour points from a crop as float32 XY coordinates."""
    arr = np.array(img.convert("L"), dtype=np.uint8)
    if arr.size == 0:
        return None

    _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cv2.countNonZero(bw) > bw.size // 2:
        bw = cv2.bitwise_not(bw)

    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < float(min_area):
        return None

    pts = contour.reshape(-1, 2).astype(np.float32)
    if pts.shape[0] < 8:
        return None
    return pts


def _estimate_pointed_end_theta_deg(
    img: Image.Image,
    *,
    min_area: float = 16.0,
    ambiguity_ratio: float = 1.05,
    lo_pct: float = 20.0,
    hi_pct: float = 80.0,
) -> Optional[float]:
    """Estimate heading by selecting the narrower end of the dominant axis.

    Uses multiple end-windows and a majority vote so a noisy contour edge does not
    dominate the decision for elongated objects.
    """
    pts = _extract_primary_contour_points(img, min_area=min_area)
    if pts is None:
        return None

    center = np.mean(pts, axis=0)
    centered = pts - center
    cov = np.cov(centered, rowvar=False)
    if cov.shape != (2, 2):
        return None

    eigvals, eigvecs = np.linalg.eigh(cov)
    idx = int(np.argmax(eigvals))
    major = eigvecs[:, idx].astype(np.float32)
    nrm = float(np.linalg.norm(major))
    if nrm <= 1e-6:
        return None
    major /= nrm
    minor = np.array([-major[1], major[0]], dtype=np.float32)

    t = centered @ major
    s = centered @ minor

    def _robust_width(vals: np.ndarray) -> float:
        return float(np.percentile(vals, 95.0) - np.percentile(vals, 5.0))

    # Evaluate several windows near both ends. This is more stable than relying
    # on one percentile cut when the silhouette has local noise/clutter.
    windows = (
        (max(2.0, lo_pct - 12.0), lo_pct),
        (max(2.0, lo_pct - 6.0), lo_pct + 4.0),
        (max(2.0, lo_pct - 2.0), lo_pct + 8.0),
    )
    low_ws: list[float] = []
    high_ws: list[float] = []
    votes = 0
    for low_a, low_b in windows:
        high_a = 100.0 - low_b
        high_b = 100.0 - low_a
        t_lo_a = float(np.percentile(t, low_a))
        t_lo_b = float(np.percentile(t, low_b))
        t_hi_a = float(np.percentile(t, high_a))
        t_hi_b = float(np.percentile(t, high_b))

        low_end = s[(t >= t_lo_a) & (t <= t_lo_b)]
        high_end = s[(t >= t_hi_a) & (t <= t_hi_b)]
        if low_end.size < 4 or high_end.size < 4:
            continue

        low_w = max(1e-6, _robust_width(low_end))
        high_w = max(1e-6, _robust_width(high_end))
        low_ws.append(low_w)
        high_ws.append(high_w)
        if high_w < low_w:
            votes += 1
        elif low_w < high_w:
            votes -= 1

    if not low_ws or not high_ws:
        return None

    low_w = float(np.median(np.array(low_ws, dtype=np.float32)))
    high_w = float(np.median(np.array(high_ws, dtype=np.float32)))
    width_ratio = max(low_w, high_w) / min(low_w, high_w)
    if width_ratio < float(ambiguity_ratio):
        return None

    # Require directional agreement across windows for robustness.
    if abs(votes) < 1:
        return None

    nose_is_high_end = votes > 0
    heading_vec = major if nose_is_high_end else -major
    theta = (float(np.degrees(np.arctan2(heading_vec[1], heading_vec[0]))) + 360.0) % 360.0
    return theta


def _estimate_tip_vertex_theta_deg(
    img: Image.Image,
    *,
    min_area: float = 16.0,
    epsilon_ratio: float = 0.02,
) -> Optional[float]:
    """Estimate heading by selecting the sharpest convex-hull vertex.

    This fallback helps vessels where side-width asymmetry is weak, but the bow tip
    remains geometrically sharp relative to the stern.
    """
    arr = np.array(img.convert("L"), dtype=np.uint8)
    if arr.size == 0:
        return None

    _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cv2.countNonZero(bw) > bw.size // 2:
        bw = cv2.bitwise_not(bw)

    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < float(min_area):
        return None

    hull = cv2.convexHull(contour)
    peri = float(cv2.arcLength(hull, True))
    eps = max(1.0, float(epsilon_ratio) * peri)
    poly = cv2.approxPolyDP(hull, eps, True).reshape(-1, 2).astype(np.float32)
    if poly.shape[0] < 3:
        return None

    center = np.mean(poly, axis=0)

    best_score = -1.0
    best_vec = None
    n = poly.shape[0]
    for i in range(n):
        p_prev = poly[(i - 1) % n]
        p = poly[i]
        p_next = poly[(i + 1) % n]
        v1 = p_prev - p
        v2 = p_next - p
        n1 = float(np.linalg.norm(v1))
        n2 = float(np.linalg.norm(v2))
        if n1 <= 1e-6 or n2 <= 1e-6:
            continue

        c = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
        angle = float(np.arccos(c))  # smaller -> sharper tip
        radial = float(np.linalg.norm(p - center))
        score = max(0.0, (np.pi - angle)) * radial
        if score > best_score:
            best_score = score
            best_vec = (p - center)

    if best_vec is None:
        return None

    nrm = float(np.linalg.norm(best_vec))
    if nrm <= 1e-6:
        return None
    best_vec = best_vec / nrm
    theta = (float(np.degrees(np.arctan2(best_vec[1], best_vec[0]))) + 360.0) % 360.0
    return theta


def estimate_airplane_nose_theta_deg(img: Image.Image) -> Optional[float]:
    """Estimate airplane nose heading from crop silhouette in degrees [0, 360)."""
    return _estimate_pointed_end_theta_deg(
        img,
        min_area=16.0,
        ambiguity_ratio=1.03,
        lo_pct=18.0,
        hi_pct=82.0,
    )


def estimate_vessel_nose_theta_deg(img: Image.Image) -> Optional[float]:
    """Estimate vessel *nose* heading from crop silhouette in degrees [0, 360).

    The method fits the dominant axis with PCA, then compares silhouette width near
    both ends of that axis. The narrower end is treated as the vessel nose.
    Returns ``None`` when geometry is too ambiguous.
    """
    theta = _estimate_pointed_end_theta_deg(
        img,
        min_area=16.0,
        ambiguity_ratio=1.03,
        lo_pct=16.0,
        hi_pct=84.0,
    )
    if theta is not None:
        return theta

    # Fallback for near-symmetric hulls where side-width cue is weak.
    return _estimate_tip_vertex_theta_deg(img, min_area=16.0, epsilon_ratio=0.02)


def encode_airplane_symbol_v1(
    img: Image.Image,
    zlib_level: int = 9,
    *,
    category_id: Optional[int] = None,
    theta_deg: Optional[float] = None,
) -> bytes:
    """Encode symbol payload with category and quantized orientation.

    Payload (2 bytes):
      - byte0: category_id (uint8)
      - byte1: theta quantized from [0, 360) to [0, 255]

    If ``theta_deg`` is provided, it overrides image-based orientation estimation.
    """
    _ = zlib_level
    theta_val = _estimate_major_axis_theta_deg(img) if theta_deg is None else float(theta_deg) % 360.0
    theta_q = int(np.clip(round((theta_val / 360.0) * 255.0), 0, 255))
    if category_id is None:
        category_q = 0
    else:
        category_q = int(np.clip(int(category_id), 0, 255))
    return bytes((category_q, theta_q))


def encode_mono_shape_v1(
    img: Image.Image,
    zlib_level: int = 9,
    *,
    max_points: int = 64,
    epsilon_ratio: float = 0.02,
) -> bytes:
    """Encode one simplified object contour as a compact polygon payload.

    Payload layout before zlib:
    - uint8: version (1)
    - uint8: number of points N
    - N * (uint8 qx, uint8 qy) quantized to crop-local coordinates
    """
    if max_points <= 0:
        raise ValueError(f"max_points must be > 0, got {max_points}")

    arr = np.array(img.convert("L"), dtype=np.uint8)
    h, w = arr.shape
    if h <= 1 or w <= 1:
        return zlib.compress(bytes((1, 0)), level=zlib_level)

    _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cv2.countNonZero(bw) > bw.size // 2:
        bw = cv2.bitwise_not(bw)

    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return zlib.compress(bytes((1, 0)), level=zlib_level)

    contour = max(contours, key=cv2.contourArea)
    peri = float(cv2.arcLength(contour, True))
    eps = max(1.0, float(epsilon_ratio) * peri)
    approx = cv2.approxPolyDP(contour, eps, True).reshape(-1, 2)

    if approx.shape[0] < 3:
        ys, xs = np.where(bw > 0)
        if xs.size >= 2:
            x1, y1 = int(xs.min()), int(ys.min())
            x2, y2 = int(xs.max()), int(ys.max())
            approx = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.int32)
        else:
            return zlib.compress(bytes((1, 0)), level=zlib_level)

    if approx.shape[0] > max_points:
        idx = np.linspace(0, approx.shape[0] - 1, num=max_points, dtype=np.int32)
        approx = approx[idx]

    def _q(coord: int, max_coord: int) -> int:
        if max_coord <= 0:
            return 0
        return int(np.clip(round((coord * 255.0) / max_coord), 0, 255))

    pts = [(_q(int(x), w - 1), _q(int(y), h - 1)) for x, y in approx]
    n = min(len(pts), 255)
    header = bytes((1, n))
    body = b"".join(bytes((x, y)) for x, y in pts[:n])
    return zlib.compress(header + body, level=zlib_level)

# ----------------- helpers -------------------------------------
def _pack_bits(values: np.ndarray, bits: int) -> tuple[bytes, int]:
    """Pack fixed-width integer values into a byte stream.

    Args:
        values: 1D array-like sequence of non-negative integer values.
        bits: Number of bits per value (must evenly divide 8, e.g. 1, 2, 4, 8).

    Returns:
        A tuple ``(packed_bytes, pad_count)`` where ``packed_bytes`` is the packed
        byte stream and ``pad_count`` is the number of zero values appended to align
        to full bytes.

    Raises:
        ValueError: If any value exceeds the representable range for ``bits``.
    """
    raw_values = np.asarray(values)
    max_value = (1 << bits) - 1
    try:
        if np.any(raw_values < 0) or np.any(raw_values > max_value):
            raise ValueError("values out of range for bit width")
    except TypeError as exc:
        raise ValueError("values must be numeric and within range for bit width") from exc

    values = raw_values.astype(np.uint8, copy=False)
    per_byte = 8 // bits
    pad = (-len(values)) % per_byte
    if pad:
        values = np.concatenate([values, np.zeros(pad, dtype=np.uint8)])
    values = values.reshape(-1, per_byte)
    packed = np.zeros(values.shape[0], dtype=np.uint8)
    for i in range(per_byte):
        packed |= values[:, i] << (bits * i)
    return packed.tobytes(), pad

def encode_mono_8bit_template_drop1bit(
    img: Image.Image,
    zlib_level: int = 9,
    *,
    two_bit_run: int = 4,
    one_bit_run: int = 1,
    skip_mask: Optional[Image.Image] = None,
) -> bytes:
    """Encode by area-downsampling to ratio n/(n+m) height then 8-bit packing.

    Same as mono-2bit-template-drop1bit but uses full 8-bit precision for kept pixels
    instead of 2-bit quantization. Decoder recovers full resolution via bicubic upsampling.
    skip_mask pixels are zeroed before downsampling so those regions encode as black
    (they will be overwritten by object crops at the compositing stage).
    """
    if two_bit_run <= 0:
        raise ValueError(f"two_bit_run must be > 0, got {two_bit_run}")
    if one_bit_run <= 0:
        raise ValueError(f"one_bit_run must be > 0, got {one_bit_run}")

    img = img.convert("L")

    if skip_mask is not None:
        skip_arr = (np.array(skip_mask.convert("L"), dtype=np.uint8) > 0)
        if skip_arr.shape != (img.height, img.width):
            raise ValueError(
                f"skip_mask size mismatch: expected {(img.width, img.height)}, got {skip_mask.size}"
            )
        arr = np.array(img, dtype=np.uint8)
        arr[skip_arr] = 0
        img = Image.fromarray(arr, mode="L")

    ratio = float(two_bit_run) / float(two_bit_run + one_bit_run)
    new_h = max(1, int(round(img.height * ratio)))
    img_sub = img.resize((img.width, new_h), Image.Resampling.BOX)

    # Store full 8-bit values (no quantization)
    flat = np.array(img_sub, dtype=np.uint8).flatten()

    payload = flat.tobytes()
    return zlib.compress(payload, level=zlib_level)
