# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: decoder/codecs.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: Low-level decoder codec implementations.
"""

import subprocess  # nosec B404 - used only to invoke the fixed 'avifdec' binary with an argv list, no shell
import tempfile
from pathlib import Path
from typing import Optional
import zlib
import cv2
import numpy as np
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Icon images loaded once from disk
# ---------------------------------------------------------------------------
_OBJ_ICONS_DIR = Path(__file__).parent / "obj_icons"
_JET_ICON_PATH = _OBJ_ICONS_DIR / "jet.png"
_VESSEL_ICON_PATH = _OBJ_ICONS_DIR / "vessel.png"

# Detect best available resampling filter at module load time
def _get_best_resample_filter():
    """Return the best available resampling filter, or BICUBIC as fallback.

    Note: This function is called at module import time, so it must never raise.
    """
    try:
        # BICUBIC is always safe and high-quality
        return Image.Resampling.BICUBIC
    except Exception:
        # Fallback to numeric constant if enum fails completely
        return 3  # BICUBIC

_BEST_RESAMPLE_FILTER = _get_best_resample_filter()

def _load_jet_icon() -> Image.Image:
    """Load jet.png in RGBA mode; returns a minimal 1×1 RGBA fallback on failure."""
    try:
        img = Image.open(_JET_ICON_PATH).convert("RGBA")
        return img
    except Exception:
        fallback = Image.new("RGBA", (1, 1), color=(255, 255, 255, 255))
        return fallback

def _load_vessel_icon() -> Image.Image:
    """Load vessel.png in RGBA mode; returns a minimal 1×1 RGBA fallback on failure."""
    try:
        img = Image.open(_VESSEL_ICON_PATH).convert("RGBA")
        return img
    except Exception:
        fallback = Image.new("RGBA", (1, 1), color=(255, 255, 255, 255))
        return fallback

_JET_ICON: Image.Image = _load_jet_icon()
_VESSEL_ICON: Image.Image = _load_vessel_icon()


# ---------------------------------
# AVIF decoding
# ---------------------------------
def decode_avif(data: bytes, timeout_sec: int = 120, color: bool = True) -> Image.Image:
    """Decode AVIF bytes into PIL image using the external ``avifdec`` tool.
    
    Args:
        data: AVIF encoded bytes.
        timeout_sec: Timeout for avifdec subprocess (default 120 seconds).
        color: If True, force output to RGB (color-avif). If False, force to L (mono-avif).

    Returns:
        Decoded PIL Image in the correct mode matching the encoder.

    Raises:
        FileNotFoundError: avifdec executable not found on PATH.
        RuntimeError: avifdec failed or timed out.
    """
    with tempfile.TemporaryDirectory(prefix="semantic_img_comp_avifdec_") as temp_dir:
        temp_dir_path = Path(temp_dir)
        avif_in = temp_dir_path / "input.avif"
        png_out = temp_dir_path / "output.png"
        avif_in.write_bytes(data)

        cmd = ["avifdec", str(avif_in), str(png_out)]
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
                "The 'avifdec' executable was not found on PATH. "
                "Install libavif tools or make avifdec available before using AVIF decoders."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("avifdec timed out while decoding an image") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(
                f"avifdec failed with exit code {exc.returncode}: {stderr or 'no stderr output'}"
            ) from exc

        if not png_out.exists():
            raise RuntimeError("avifdec completed without producing output image")

        img = Image.open(png_out)
        img.load()
        img = img.copy()

    # Explicitly convert to the expected mode matching the encoder.
    # Without this, avifdec may return L for YUV400 or RGB for YUV420, but PIL
    # mode depends on what avifdec wrote — not guaranteed to match codec intent.
    return img.convert("RGB") if color else img.convert("L")


# ---------------------------------
# 2-bit decoding
# ---------------------------------
def decode_color_2bit(data, obj_scaled_size=None):
    w, h = _validate_size(obj_scaled_size, field_name="obj_scaled_size")
    total_pixels = w * h
    packed_all = np.frombuffer(zlib.decompress(data), dtype=np.uint8)

    padded_pixels = ((total_pixels + 3) // 4) * 4
    bytes_per_channel = padded_pixels // 4
    expected_len = bytes_per_channel * 3
    _require_length(len(packed_all), expected_len, "color-2bit")

    channels = []

    for c in range(3):
        packed = packed_all[c * bytes_per_channel:(c + 1) * bytes_per_channel]

        arr = np.empty(padded_pixels, dtype=np.uint8)

        arr[0::4] = (packed >> 6) & 3
        arr[1::4] = (packed >> 4) & 3
        arr[2::4] = (packed >> 2) & 3
        arr[3::4] = packed & 3

        arr = arr[:total_pixels]

        channels.append(arr)

    rgb = np.stack(channels, axis=1)
    rgb = (rgb * 85).astype(np.uint8)
    rgb = rgb.reshape(h, w, 3)

    return Image.fromarray(rgb, mode="RGB")


def decode_mono_2bit(data, obj_scaled_size=None, *, max_level: int = 255, skip_mask=None):
    w, h = _validate_size(obj_scaled_size, field_name="obj_scaled_size")
    total_pixels = w * h
    max_level = _validate_max_level(max_level)

    raw = zlib.decompress(data)
    packed = np.frombuffer(raw, dtype=np.uint8)

    padded_pixels = ((total_pixels + 3) // 4) * 4
    expected_len = padded_pixels // 4

    if len(packed) == expected_len:
        arr = np.empty(padded_pixels, dtype=np.uint8)
        arr[0::4] = (packed >> 6) & 3
        arr[1::4] = (packed >> 4) & 3
        arr[2::4] = (packed >> 2) & 3
        arr[3::4] = packed & 3
        arr = arr[:total_pixels]
    else:
        if len(packed) < 2 or int(packed[0]) != 255:
            raise ValueError("Invalid mono-2bit sparse payload marker")
        if skip_mask is None:
            raise ValueError("mono-2bit sparse payload requires skip_mask")

        pad = int(packed[1])
        if pad < 0 or pad > 3:
            raise ValueError(f"Invalid mono-2bit sparse pad value: {pad}")

        skip_arr = (np.array(skip_mask.convert("L"), dtype=np.uint8) > 0).flatten()
        if skip_arr.size != total_pixels:
            raise ValueError(
                f"skip_mask size mismatch: expected {total_pixels} pixels for size {obj_scaled_size}, got {skip_arr.size}"
            )
        keep = (skip_arr == 0)
        kept_count = int(keep.sum())
        expected_sparse_len = (kept_count + pad + 3) // 4  # ceiling division for 4-pixel alignment
        sparse_packed = packed[2:]
        if len(sparse_packed) < expected_sparse_len:
            _require_length(len(sparse_packed), expected_sparse_len, "mono-2bit-sparse")
        elif len(sparse_packed) > expected_sparse_len:
            # Allow trailing bytes for mixed-version streams where skip-mask
            # reconstruction differs slightly between encoder/decoder.
            sparse_packed = sparse_packed[:expected_sparse_len]

        arr_kept = np.empty(kept_count + pad, dtype=np.uint8)
        arr_kept[0::4] = (sparse_packed >> 6) & 3
        arr_kept[1::4] = (sparse_packed >> 4) & 3
        arr_kept[2::4] = (sparse_packed >> 2) & 3
        arr_kept[3::4] = sparse_packed & 3
        arr_kept = arr_kept[:kept_count]

        arr = np.zeros(total_pixels, dtype=np.uint8)
        arr[keep] = arr_kept

    arr = ((arr.astype(np.uint16) * max_level) // 3).astype(np.uint8)

    return Image.fromarray(arr.reshape((h, w)), mode="L")


def decode_mono_2bit_mixed_n1bit(
    data,
    obj_scaled_size=None,
    *,
    two_bit_run: int = 4,
    one_bit_run: int = 1,
    max_level: int = 255,
    skip_mask=None,
):
    if two_bit_run <= 0:
        raise ValueError(f"two_bit_run must be > 0, got {two_bit_run}")
    if one_bit_run <= 0:
        raise ValueError(f"one_bit_run must be > 0, got {one_bit_run}")

    w, h = _validate_size(obj_scaled_size, field_name="obj_scaled_size")
    total_pixels = w * h
    max_level = _validate_max_level(max_level)

    raw = np.frombuffer(zlib.decompress(data), dtype=np.uint8)
    if raw.size < 2:
        raise ValueError("Corrupt stream: too small for mono-2bit-mixed header")

    pos = 0
    sparse = int(raw[0]) == 255
    if sparse:
        if skip_mask is None:
            raise ValueError("mono-2bit-mixed sparse payload requires skip_mask")
        if raw.size < 3:
            raise ValueError("Corrupt stream: too small for mono-2bit-mixed sparse header")
        pos = 1

    pad_2 = int(raw[pos])
    pad_1 = int(raw[pos + 1])
    pos += 2
    if pad_2 < 0 or pad_2 > 3:
        raise ValueError(f"Invalid mono-2bit-mixed 2-bit pad value: {pad_2}")
    if pad_1 < 0 or pad_1 > 7:
        raise ValueError(f"Invalid mono-2bit-mixed 1-bit pad value: {pad_1}")

    if sparse:
        skip_arr = (np.array(skip_mask.convert("L"), dtype=np.uint8) > 0).flatten()
        if skip_arr.size != total_pixels:
            raise ValueError(
                f"skip_mask size mismatch: expected {total_pixels} pixels for size {obj_scaled_size}, got {skip_arr.size}"
            )
        keep = (skip_arr == 0)
        stream_count = int(keep.sum())
    else:
        keep = None
        stream_count = total_pixels

    cycle = int(two_bit_run + one_bit_run)
    idx = np.arange(stream_count, dtype=np.int64)
    two_bit_sel = (idx % cycle) < int(two_bit_run)
    n2 = int(np.sum(two_bit_sel))
    n1 = int(stream_count - n2)

    expected_len_2 = (n2 + pad_2 + 3) // 4
    expected_len_1 = (n1 + pad_1 + 7) // 8

    if raw.size < pos + expected_len_2 + expected_len_1:
        raise ValueError("Corrupt stream: missing mono-2bit-mixed payload")

    packed_2 = raw[pos: pos + expected_len_2].tobytes()
    pos += expected_len_2
    packed_1 = raw[pos: pos + expected_len_1].tobytes()

    vals_2 = _unpack_bits(packed_2, 2, n2).astype(np.uint8)
    vals_1 = _unpack_bits(packed_1, 1, n1).astype(np.uint8) * 3

    stream_vals = np.empty(stream_count, dtype=np.uint8)
    stream_vals[two_bit_sel] = vals_2
    stream_vals[~two_bit_sel] = vals_1

    if sparse:
        arr = np.zeros(total_pixels, dtype=np.uint8)
        arr[keep] = stream_vals
    else:
        arr = stream_vals

    arr = ((arr.astype(np.uint16) * max_level) // 3).astype(np.uint8)
    return Image.fromarray(arr.reshape((h, w)), mode="L")


def decode_mono_2bit_template_drop1bit(
    data,
    obj_scaled_size=None,
    *,
    two_bit_run: int = 4,
    one_bit_run: int = 1,
    max_level: int = 255,
    skip_mask=None,
    fill_gray_level: int = 128,  # no longer used; kept for call-site compatibility
    neighbor_k: int = 2,         # no longer used; kept for call-site compatibility
):
    """Decode by 2-bit unpack of area-downsampled image then bicubic upsampling to full size."""
    if two_bit_run <= 0:
        raise ValueError(f"two_bit_run must be > 0, got {two_bit_run}")
    if one_bit_run <= 0:
        raise ValueError(f"one_bit_run must be > 0, got {one_bit_run}")

    w, h = _validate_size(obj_scaled_size, field_name="obj_scaled_size")
    max_level = _validate_max_level(max_level)

    ratio = float(two_bit_run) / float(two_bit_run + one_bit_run)
    new_h = max(1, int(round(h * ratio)))
    total_small = w * new_h

    raw = np.frombuffer(zlib.decompress(data), dtype=np.uint8)
    if raw.size < 1:
        raise ValueError("Corrupt stream: too small for mono-2bit-template-drop1bit header")

    pad = int(raw[0])
    if pad < 0 or pad > 3:
        raise ValueError(f"Invalid mono-2bit-template-drop1bit pad value: {pad}")

    expected_len = (total_small + 3) // 4
    if raw.size - 1 < expected_len:
        raise ValueError("Corrupt stream: missing mono-2bit-template-drop1bit payload")

    vals = _unpack_bits(raw[1:].tobytes(), 2, total_small).astype(np.uint8)
    vals = ((vals.astype(np.uint16) * max_level) // 3).astype(np.uint8)

    small_img = Image.fromarray(vals.reshape((new_h, w)), mode="L")
    return small_img.resize((w, h), Image.Resampling.BICUBIC)


# ---------------------------------
# 4-bit decoding
# ---------------------------------
def decode_color_4bit(data: bytes, obj_scaled_size=None):
    w, h = _validate_size(obj_scaled_size, field_name="obj_scaled_size")
    total_vals = w * h * 3

    packed = np.frombuffer(zlib.decompress(data), dtype=np.uint8)

    padded_vals = ((total_vals + 1) // 2) * 2
    expected_len = padded_vals // 2
    _require_length(len(packed), expected_len, "color-4bit")

    arr = np.empty(padded_vals, dtype=np.uint8)

    arr[0::2] = (packed >> 4) & 0x0F
    arr[1::2] = packed & 0x0F

    arr = arr[:total_vals]

    arr = (arr * 17).astype(np.uint8)

    img = arr.reshape((h, w, 3))

    return Image.fromarray(img, mode="RGB")


def decode_mono_4bit(data: bytes, obj_scaled_size=None):
    w, h = _validate_size(obj_scaled_size, field_name="obj_scaled_size")
    total_pixels = w * h

    packed = np.frombuffer(zlib.decompress(data), dtype=np.uint8)

    padded_pixels = ((total_pixels + 1) // 2) * 2
    expected_len = padded_pixels // 2
    _require_length(len(packed), expected_len, "mono-4bit")

    arr = np.empty(padded_pixels, dtype=np.uint8)

    arr[0::2] = (packed >> 4) & 0x0F
    arr[1::2] = packed & 0x0F

    arr = arr[:total_pixels]

    arr = (arr * 17).astype(np.uint8)

    return Image.fromarray(arr.reshape((h, w)), mode="L")


# ---------------------------------
# 8-bit decoding
# ---------------------------------
def decode_color_8bit(data: bytes, size: tuple):
    w, h = _validate_size(size, field_name="size")

    raw = zlib.decompress(data)
    expected_len = w * h * 3
    _require_length(len(raw), expected_len, "color-8bit")

    arr = np.frombuffer(raw, dtype=np.uint8)
    arr = arr.reshape((h, w, 3))

    return Image.fromarray(arr, mode="RGB")


def decode_mono_8bit(data: bytes, size: tuple):
    w, h = _validate_size(size, field_name="size")

    raw = zlib.decompress(data)
    expected_len = w * h
    _require_length(len(raw), expected_len, "mono-8bit")

    arr = np.frombuffer(raw, dtype=np.uint8)
    arr = arr.reshape((h, w))

    return Image.fromarray(arr, mode="L")

# ---------------------------------
# 2/8-bit decoding
# ---------------------------------
def decode_color_28bit(compressed, img_shape, *, smooth_sigma: Optional[float] = 1.0, return_masks=True):
    w, h = img_shape
    n_expected = h * w

    mv = np.frombuffer(zlib.decompress(compressed), dtype=np.uint8)
    if len(mv) < 6:
        raise ValueError("Corrupt stream: too small for header")

    mask_8_pad = int(np.frombuffer(mv[0:1], dtype=np.uint8)[0])
    q2_pad = int(np.frombuffer(mv[1:2], dtype=np.uint8)[0])
    n8 = int(np.frombuffer(mv[2:6], dtype=np.uint32)[0])

    n_stream = n_expected
    n2 = n_stream - n8
    if n2 < 0:
        raise ValueError("Corrupt stream: n8 > total pixels implied by img_shape")

    mask_count = n_stream + mask_8_pad
    mask_bytes = (mask_count + 7) // 8
    pos = 6
    if len(mv) < pos + mask_bytes:
        raise ValueError("Corrupt stream: missing 8-bit mask")

    mask_8_packed = mv[pos: pos + mask_bytes].tobytes()
    pos += mask_bytes
    cls_flat = _unpack_bits(mask_8_packed, 1, n_stream).astype(np.uint8)
    if n8 != int((cls_flat == 1).sum()) or n2 != int((cls_flat == 0).sum()):
        raise ValueError("Corrupt stream: payload counts do not match mask")

    cls_img = cls_flat.reshape((h, w))

    n8_bytes = n8 * 3
    if len(mv) < pos + n8_bytes:
        raise ValueError("Corrupt stream: missing 8-bit RGB payload")
    vals_8 = np.frombuffer(mv[pos: pos + n8_bytes], dtype=np.uint8).reshape(n8, 3)
    pos += n8_bytes

    q2_symbols = n2 * 3
    q2_count = q2_symbols + q2_pad
    q2_bytes = (q2_count + 3) // 4
    if len(mv) < pos + q2_bytes:
        raise ValueError("Corrupt stream: missing 2-bit payload")
    q2_packed = mv[pos: pos + q2_bytes].tobytes()
    pos += q2_bytes

    if pos != len(mv):
        raise ValueError(f"Corrupt stream: trailing bytes (pos={pos}, total={len(mv)})")

    q2 = _unpack_bits(q2_packed, 2, q2_symbols).astype(np.uint8).reshape(n2, 3)
    vals_2 = (q2.astype(np.uint16) * 85).astype(np.uint8)

    out = np.empty((n_stream, 3), dtype=np.uint8)
    out[cls_flat == 1] = vals_8
    out[cls_flat == 0] = vals_2
    out_img = out.reshape((h, w, 3))

    if smooth_sigma and smooth_sigma > 0:
        mask2 = (cls_img == 0).astype(np.float32)
        sigma = float(smooth_sigma)
        smoothed = out_img.astype(np.float32)

        for c in range(3):
            imgf = out_img[:, :, c].astype(np.float32)
            num = cv2.GaussianBlur(imgf * mask2, (0, 0), sigma)
            den = cv2.GaussianBlur(mask2, (0, 0), sigma)
            sm2 = num / (den + 1e-6)
            ch = smoothed[:, :, c]
            ch[cls_img == 0] = sm2[cls_img == 0]
            ch[cls_img == 1] = imgf[cls_img == 1]
            smoothed[:, :, c] = ch

        smoothed_u8 = np.clip(smoothed, 0, 255).astype(np.uint8)
    else:
        smoothed_u8 = out_img

    result_img = Image.fromarray(smoothed_u8, mode="RGB")
    if return_masks:
        return result_img, cls_img
    return result_img

def decode_mono_28bit(compressed, img_shape, *, smooth_sigma: Optional[float] = 1.0, return_masks=True):
    w, h = img_shape
    n_expected = h * w

    mv = np.frombuffer(zlib.decompress(compressed), dtype=np.uint8)
    if len(mv) < 6:
        raise ValueError("Corrupt stream: too small for header")

    mask_8_pad = int(np.frombuffer(mv[0:1], dtype=np.uint8)[0])
    q2_pad = int(np.frombuffer(mv[1:2], dtype=np.uint8)[0])
    n8 = int(np.frombuffer(mv[2:6], dtype=np.uint32)[0])
    n_stream = n_expected
    n2 = n_stream - n8
    if n2 < 0:
        raise ValueError("Corrupt stream: n8 > total pixels implied by img_shape")

    mask_count = n_stream + mask_8_pad
    mask_bytes = (mask_count + 7) // 8

    pos = 6
    if len(mv) < pos + mask_bytes:
        raise ValueError("Corrupt stream: missing 8-bit mask")

    mask_8_packed = mv[pos: pos + mask_bytes].tobytes()
    pos += mask_bytes
    cls_flat = _unpack_bits(mask_8_packed, 1, n_stream).astype(np.uint8)

    if n8 != int((cls_flat == 1).sum()) or n2 != int((cls_flat == 0).sum()):
        raise ValueError("Corrupt stream: payload counts do not match mask")

    cls_img = cls_flat.reshape((h, w))

    if len(mv) < pos + n8:
        raise ValueError("Corrupt stream: missing 8-bit payload")
    vals_8 = np.frombuffer(mv[pos: pos + n8], dtype=np.uint8)
    pos += n8

    q2_count = n2 + q2_pad
    q2_bytes = (q2_count + 3) // 4
    if len(mv) < pos + q2_bytes:
        raise ValueError("Corrupt stream: missing 2-bit payload")
    q2_packed = mv[pos: pos + q2_bytes].tobytes()
    pos += q2_bytes

    if pos != len(mv):
        raise ValueError(f"Corrupt stream: trailing bytes (pos={pos}, total={len(mv)})")

    q2 = _unpack_bits(q2_packed, 2, n2).astype(np.uint8)
    vals_2 = (q2.astype(np.uint16) * 85).astype(np.uint8)

    out = np.empty(n_stream, dtype=np.uint8)
    out[cls_flat == 1] = vals_8
    out[cls_flat == 0] = vals_2
    out_img = out.reshape((h, w))

    if smooth_sigma and smooth_sigma > 0:
        mask2 = (cls_img == 0).astype(np.float32)
        imgf = out_img.astype(np.float32)
        sigma = float(smooth_sigma)
        num = cv2.GaussianBlur(imgf * mask2, (0, 0), sigma)
        den = cv2.GaussianBlur(mask2, (0, 0), sigma)
        smoothed2 = num / (den + 1e-6)
        smoothed = imgf.copy()
        smoothed[cls_img == 0] = smoothed2[cls_img == 0]
        smoothed[cls_img == 1] = imgf[cls_img == 1]
        smoothed_u8 = np.clip(smoothed, 0, 255).astype(np.uint8)
    else:
        smoothed_u8 = out_img

    result_img = Image.fromarray(smoothed_u8, mode="L")
    if return_masks:
        return result_img, cls_img
    return result_img


# ---------------------------------
# 1/8-bit decoding [mono only]
# ---------------------------------
def decode_mono_18bit(compressed, img_shape, *, smooth_sigma: Optional[float] = 1.0, return_masks=True):
    w, h = img_shape
    n_expected = h * w

    mv = np.frombuffer(zlib.decompress(compressed), dtype=np.uint8)
    if len(mv) < 6:
        raise ValueError("Corrupt stream: too small for header")

    mask_8_pad = int(mv[0])
    q1_pad = int(mv[1])
    n8 = int(np.frombuffer(mv[2:6], dtype=np.uint32)[0])
    n_stream = n_expected
    n1 = n_stream - n8
    if n1 < 0:
        raise ValueError("Corrupt stream: n8 > total pixels implied by img_shape")

    mask_count = n_stream + mask_8_pad
    mask_bytes = (mask_count + 7) // 8

    pos = 6
    if len(mv) < pos + mask_bytes:
        raise ValueError("Corrupt stream: missing 8-bit mask")
    mask_8_packed = mv[pos: pos + mask_bytes].tobytes()
    pos += mask_bytes

    cls_flat = _unpack_bits(mask_8_packed, 1, n_stream).astype(np.uint8)
    cls_img = cls_flat.reshape((h, w))

    if len(mv) < pos + n8:
        raise ValueError("Corrupt stream: missing 8-bit payload")
    vals_8 = np.frombuffer(mv[pos: pos + n8], dtype=np.uint8)
    pos += n8

    q1_count = n1 + q1_pad
    q1_bytes = (q1_count + 7) // 8
    if len(mv) < pos + q1_bytes:
        raise ValueError("Corrupt stream: missing 1-bit payload")
    q1_packed = mv[pos: pos + q1_bytes].tobytes()
    pos += q1_bytes

    if pos != len(mv):
        raise ValueError(f"Corrupt stream: trailing bytes (pos={pos}, total={len(mv)})")

    q1 = _unpack_bits(q1_packed, 1, n1).astype(np.uint8)
    vals_1 = (q1 * 255).astype(np.uint8)

    if n8 != int((cls_flat == 1).sum()) or n1 != int((cls_flat == 0).sum()):
        raise ValueError("Corrupt stream: payload counts do not match mask")

    out = np.empty(n_stream, dtype=np.uint8)
    out[cls_flat == 1] = vals_8
    out[cls_flat == 0] = vals_1
    out_img = out.reshape((h, w))

    if smooth_sigma and smooth_sigma > 0:
        mask_low = (cls_img == 0).astype(np.float32)
        imgf = out_img.astype(np.float32)
        sigma = float(smooth_sigma)
        num = cv2.GaussianBlur(imgf * mask_low, (0, 0), sigma)
        den = cv2.GaussianBlur(mask_low, (0, 0), sigma)
        smoothed_low = num / (den + 1e-6)

        smoothed = imgf.copy()
        smoothed[cls_img == 0] = smoothed_low[cls_img == 0]
        smoothed[cls_img == 1] = imgf[cls_img == 1]
        smoothed_u8 = np.clip(smoothed, 0, 255).astype(np.uint8)
    else:
        smoothed_u8 = out_img

    result_img = Image.fromarray(smoothed_u8, mode="L")
    if return_masks:
        return result_img, cls_img
    return result_img

# ---------------------------------
# 1-bit decoding of edge mask only
# ---------------------------------
def decode_mono_mask_1bit(
    compressed,
    img_shape,
    *,
    smooth_sigma: Optional[float] = None,
    return_masks=True,
    max_level: int = 255,
    skip_mask=None,
):
    w, h = _validate_size(img_shape, field_name="img_shape")
    n_expected = h * w
    max_level = _validate_max_level(max_level)

    mv = np.frombuffer(zlib.decompress(compressed), dtype=np.uint8)
    if len(mv) < 2:
        raise ValueError("Corrupt stream: too small for header")

    marker = int(mv[0])
    mask_pad = int(mv[1])
    pos = 2

    if marker == 255:
        if skip_mask is None:
            raise ValueError("mono-mask-1bit sparse payload requires skip_mask")
        if mask_pad < 0 or mask_pad > 7:
            raise ValueError(f"Invalid mono-mask-1bit sparse pad value: {mask_pad}")

        skip_arr = (np.array(skip_mask.convert("L"), dtype=np.uint8) > 0).flatten()
        if skip_arr.size != n_expected:
            raise ValueError(
                f"skip_mask size mismatch: expected {n_expected} pixels for size {img_shape}, got {skip_arr.size}"
            )
        keep = (skip_arr == 0)
        kept_count = int(keep.sum())
        mask_count = kept_count + mask_pad
        mask_bytes = (mask_count + 7) // 8  # ceiling division for 1-bit alignment
        if len(mv) < pos + mask_bytes:
            raise ValueError("Corrupt stream: missing sparse 1-bit mask payload")
        mask_packed = mv[pos: pos + mask_bytes].tobytes()
        pos += mask_bytes
        # Accept trailing bytes to stay compatible with mixed-version sparse
        # streams; required mask payload was already fully consumed.

        kept_vals = _unpack_bits(mask_packed, 1, kept_count).astype(np.uint8)
        mask_flat = np.zeros(n_expected, dtype=np.uint8)
        mask_flat[keep] = kept_vals
        mask_img = mask_flat.reshape((h, w))
    else:
        if marker > 7:
            raise ValueError(f"Corrupt stream: invalid marker/pad byte {marker}")
        # Legacy dense payload: first byte is pad.
        mask_pad = marker
        mask_count = n_expected + mask_pad
        mask_bytes = (mask_count + 7) // 8
        pos = 1
        if len(mv) < pos + mask_bytes:
            raise ValueError("Corrupt stream: missing 1-bit mask payload")
        mask_packed = mv[pos: pos + mask_bytes].tobytes()
        pos += mask_bytes
        if pos != len(mv):
            raise ValueError(f"Corrupt stream: trailing bytes (pos={pos}, total={len(mv)})")
        mask_flat = _unpack_bits(mask_packed, 1, n_expected).astype(np.uint8)
        mask_img = mask_flat.reshape((h, w))

    if smooth_sigma and smooth_sigma > 0:
        # Smooth the non-edge (0-valued) regions using a weighted Gaussian blend,
        # preserving detected edge pixels (1-valued) as-is.
        imgf = (mask_img * max_level).astype(np.float32)
        mask_low = (mask_img == 0).astype(np.float32)
        sigma = float(smooth_sigma)
        num = cv2.GaussianBlur(imgf * mask_low, (0, 0), sigma)
        den = cv2.GaussianBlur(mask_low, (0, 0), sigma)
        smoothed_low = num / (den + 1e-6)
        smoothed = imgf.copy()
        smoothed[mask_img == 0] = smoothed_low[mask_img == 0]
        result_img = Image.fromarray(np.clip(smoothed, 0, max_level).astype(np.uint8), mode="L")
    else:
        result_img = Image.fromarray((mask_img * max_level).astype(np.uint8), mode="L")

    if return_masks:
        return result_img, mask_img
    return result_img


def decode_mono_skel_v1(data: bytes, obj_scaled_size=None):
    """Decode sparse skeleton-segment payload into a grayscale line-only image."""
    w, h = _validate_size(obj_scaled_size, field_name="obj_scaled_size")
    stream = zlib.decompress(data)

    if len(stream) < 2:
        raise ValueError("Corrupt stream: too small for mono-skel-v1 header")

    version = stream[0]
    if version != 1:
        raise ValueError(f"Unsupported mono-skel-v1 version: {version}")

    n_lines = int(stream[1])
    expected_len = 2 + (4 * n_lines)
    _require_length(len(stream), expected_len, "mono-skel-v1")

    out = np.zeros((h, w), dtype=np.uint8)

    def _dq(q: int, max_coord: int) -> int:
        if max_coord <= 0:
            return 0
        return int(np.clip(round((q * max_coord) / 255.0), 0, max_coord))

    pos = 2
    for _ in range(n_lines):
        qx1, qy1, qx2, qy2 = stream[pos: pos + 4]
        pos += 4
        x1 = _dq(qx1, w - 1)
        y1 = _dq(qy1, h - 1)
        x2 = _dq(qx2, w - 1)
        y2 = _dq(qy2, h - 1)
        # Draw slightly thicker anti-aliased strokes so sparse segments are easier to perceive.
        cv2.line(out, (x1, y1), (x2, y2), color=255, thickness=2, lineType=cv2.LINE_AA)

    return Image.fromarray(out, mode="L")


def decode_mono_shape_v1(data: bytes, obj_scaled_size=None):
    """Decode compact polygon payload into a grayscale contour image."""
    w, h = _validate_size(obj_scaled_size, field_name="obj_scaled_size")
    stream = zlib.decompress(data)

    if len(stream) < 2:
        raise ValueError("Corrupt stream: too small for mono-shape-v1 header")

    version = stream[0]
    if version != 1:
        raise ValueError(f"Unsupported mono-shape-v1 version: {version}")

    n_points = int(stream[1])
    expected_len = 2 + (2 * n_points)
    _require_length(len(stream), expected_len, "mono-shape-v1")

    out = np.zeros((h, w), dtype=np.uint8)
    if n_points < 2:
        return Image.fromarray(out, mode="L")

    def _dq(q: int, max_coord: int) -> int:
        if max_coord <= 0:
            return 0
        return int(np.clip(round((q * max_coord) / 255.0), 0, max_coord))

    pts = []
    pos = 2
    for _ in range(n_points):
        qx, qy = stream[pos: pos + 2]
        pos += 2
        pts.append((_dq(qx, w - 1), _dq(qy, h - 1)))

    poly = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(out, [poly], isClosed=True, color=255, thickness=2, lineType=cv2.LINE_AA)
    return Image.fromarray(out, mode="L")

# ----------------- helpers -------------------------------------

def _validate_size(size: tuple, field_name: str = "size") -> tuple[int, int]:
    if not isinstance(size, tuple) or len(size) != 2:
        raise ValueError(f"{field_name} must be a (width, height) tuple")
    w, h = size
    if not isinstance(w, int) or not isinstance(h, int):
        raise TypeError(f"{field_name} dimensions must be integers")
    if w <= 0 or h <= 0:
        raise ValueError(f"{field_name} dimensions must be > 0, got {(w, h)}")
    return w, h


def _require_length(actual: int, expected: int, field_name: str) -> None:
    if actual != expected:
        raise ValueError(
            f"Invalid decoded payload length for {field_name}: expected {expected}, got {actual}"
        )


def _validate_max_level(max_level: int) -> int:
    if not isinstance(max_level, int):
        raise TypeError(f"max_level must be an integer, got {type(max_level).__name__}")
    if max_level <= 0 or max_level > 255:
        raise ValueError(f"max_level must be in the range 1..255, got {max_level}")
    return max_level

def _unpack_bits(data: bytes, bits: int, count: int) -> np.ndarray:
    per_byte = 8 // bits
    b = np.frombuffer(data, dtype=np.uint8)
    shifts = (bits * np.arange(per_byte, dtype=np.uint8)).reshape(1, -1)
    mask = np.uint8((1 << bits) - 1)
    vals = ((b.reshape(-1, 1) >> shifts) & mask).reshape(-1)
    return vals[:count].astype(np.uint8, copy=False)

def decode_airplane_symbol_v1(data: bytes) -> tuple[int, float]:
    """Decode symbol payload into (category_id, theta_deg).

    Supported payloads:
    - empty payload (legacy): (2, 0.0)
    - 1-byte payload (legacy theta-only): (2, theta in [0, 180))
    - 2-byte payload (current): [category_id, theta_q] with theta in [0, 360)
    """
    if not data:
        return 2, 0.0

    if len(data) == 1:
        theta_q = int(data[0])
        return 2, float((theta_q / 255.0) * 180.0)

    if len(data) == 2:
        category_id = int(data[0])
        theta_q = int(data[1])
        return category_id, float((theta_q / 255.0) * 360.0)

    raise ValueError(f"Invalid airplane-symbol-v1 payload length: {len(data)}")


def render_airplane_symbol(size: tuple[int, int], theta_deg: float = 0.0) -> Image.Image:
    """Render a synthetic airplane icon into a grayscale crop canvas.

    Heading convention matches encoder symbol payloads:
    - 0 deg   -> nose points right (+x in image coordinates)
    - 90 deg  -> nose points down (+y in image coordinates)
    """
    w, h = _validate_size(size, field_name="size")
    canvas = Image.new("L", (w, h), color=0)

    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    scale = min(w, h)
    if scale <= 2:
        draw = ImageDraw.Draw(canvas)
        draw.point((int(cx), int(cy)), fill=255)
        return canvas

    # Scale jet.png to fit inside the canvas, preserving aspect ratio.
    icon = _JET_ICON
    max_dim = int(round(scale * 0.90))
    max_dim = max(1, max_dim)
    iw, ih = icon.size
    ratio = min(max_dim / max(iw, 1), max_dim / max(ih, 1))
    new_iw = max(1, int(round(iw * ratio)))
    new_ih = max(1, int(round(ih * ratio)))
    icon_resized = icon.resize((new_iw, new_ih), _BEST_RESAMPLE_FILTER)

    # Place the resized icon on a square max_dim x max_dim canvas for clean rotation.
    # Use RGBA so the transparency info survives rotation.
    square = Image.new("RGBA", (max_dim, max_dim), color=(0, 0, 0, 0))
    ox = (max_dim - new_iw) // 2
    oy = (max_dim - new_ih) // 2
    square.paste(icon_resized, (ox, oy))

    # Rotate: jet.png nose points UP in the file. Payload uses 0 deg = right.
    # To make theta=0 show nose-right, we apply a -90 deg canonical offset.
    # PIL rotate is CCW-positive; encoder uses CW-positive (standard image axes).
    pil_angle = -float(theta_deg) - 90.0
    icon_rotated = square.rotate(pil_angle, resample=_BEST_RESAMPLE_FILTER, expand=False, fillcolor=(0, 0, 0, 0))

    # Extract alpha channel from rotated RGBA — aircraft pixels are opaque, background is 0.
    # Use this as the grayscale output so the sparse overlay compositing makes the
    # aircraft shape fully visible (alpha=255 → opaque) while the background stays transparent (0).
    alpha_channel = icon_rotated.split()[3]  # PIL RGBA split: R, G, B, A

    # Paste centered onto black canvas.
    paste_x = int(round(cx - icon_rotated.width / 2.0))
    paste_y = int(round(cy - icon_rotated.height / 2.0))
    canvas.paste(alpha_channel, (paste_x, paste_y))
    return canvas

def render_tanker_symbol(size: tuple[int, int], theta_deg: float = 0.0) -> Image.Image:
    """Render vessel.png icon into the specified canvas, preserving its high quality.
    
    The vessel image is scaled to fit inside the canvas while maintaining aspect ratio,
    then rotated according to theta_deg and centered on the canvas.
    """
    w, h = _validate_size(size, field_name="size")
    canvas = Image.new("L", (w, h), color=0)

    scale = min(w, h)
    if scale <= 2:
        cx = (w - 1) / 2.0
        cy = (h - 1) / 2.0
        draw = ImageDraw.Draw(canvas)
        draw.point((int(cx), int(cy)), fill=255)
        return canvas

    # Scale vessel.png to maximize occupancy in the axis-aligned bbox while
    # preserving aspect ratio and the requested object orientation.
    icon = _VESSEL_ICON
    iw, ih = icon.size
    # Rotate using payload angle directly (user-requested behavior).
    # PIL rotate is CCW-positive; encoder payload uses CW-positive image coordinates.
    pil_angle = -float(theta_deg)
    angle_rad = np.deg2rad(abs(pil_angle))
    cos_a = float(abs(np.cos(angle_rad)))
    sin_a = float(abs(np.sin(angle_rad)))

    rot_w = (iw * cos_a) + (ih * sin_a)
    rot_h = (iw * sin_a) + (ih * cos_a)
    fit_ratio = min(w / max(rot_w, 1e-6), h / max(rot_h, 1e-6))

    new_iw = max(1, int(round(iw * fit_ratio)))
    new_ih = max(1, int(round(ih * fit_ratio)))
    icon_resized = icon.resize((new_iw, new_ih), _BEST_RESAMPLE_FILTER)

    # Rotate in a full-size canvas so the oriented object stays centered in the bbox.
    layer = Image.new("RGBA", (w, h), color=(0, 0, 0, 0))
    ox = (w - new_iw) // 2
    oy = (h - new_ih) // 2
    layer.paste(icon_resized, (ox, oy))
    icon_rotated = layer.rotate(pil_angle, resample=_BEST_RESAMPLE_FILTER, expand=False, fillcolor=(0, 0, 0, 0))

    # Preserve vessel details by using luminance inside the foreground alpha mask.
    # Some vessel assets carry rich grayscale/color details with a mostly uniform alpha.
    gray_channel = icon_rotated.convert("L")
    alpha_channel = icon_rotated.getchannel("A")
    gray_arr = np.array(gray_channel, dtype=np.uint8)
    alpha_arr = np.array(alpha_channel, dtype=np.uint8)
    detail_arr = ((gray_arr.astype(np.uint16) * alpha_arr.astype(np.uint16)) // 255).astype(np.uint8)

    # If the icon interior is effectively flat after conversion, fall back to alpha-only
    # rendering to keep legacy behavior for mask-like assets.
    alpha_nonzero = alpha_arr > 0
    if np.any(alpha_nonzero):
        detail_vals = detail_arr[alpha_nonzero]
        if int(detail_vals.max()) - int(detail_vals.min()) < 8:
            detail_arr = alpha_arr
    else:
        detail_arr = alpha_arr
    symbol_channel = Image.fromarray(detail_arr, mode="L")

    canvas.paste(symbol_channel, (0, 0))
    return canvas

