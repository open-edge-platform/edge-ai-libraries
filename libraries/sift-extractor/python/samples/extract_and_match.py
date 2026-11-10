#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Extract and match SIFT features on real image(s) with the Python bindings.

Always runs extract on both views, then Lowe-ratio match.

Examples:
  # One image → affine pair (30° / 0.85), extract both, then match:
  python python/samples/extract_and_match.py scene.pgm

  # Two real views:
  python python/samples/extract_and_match.py left.png right.png

  python python/samples/extract_and_match.py a.pgm b.pgm --backend opencl --ratio 0.8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import sift_extractor


def load_pgm(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if not data.startswith(b"P5"):
        raise ValueError(f"only binary PGM P5 is supported without OpenCV/PIL: {path}")
    values: list[int] = []
    i = 2
    while i < len(data) and len(values) < 3:
        while i < len(data) and data[i] in b" \t\r\n":
            i += 1
        if i < len(data) and data[i] == ord("#"):
            while i < len(data) and data[i] not in b"\r\n":
                i += 1
            continue
        start = i
        while i < len(data) and data[i] not in b" \t\r\n":
            i += 1
        values.append(int(data[start:i]))
    # P5: exactly one whitespace after maxval; further bytes are raster (may be
    # 0x20/0x09/0x0d and must not be treated as header separators).
    if i >= len(data) or data[i] not in b" \t\r\n":
        raise ValueError(f"PGM header missing whitespace before raster: {path}")
    i += 1
    width, height, max_value = values
    if max_value <= 0 or max_value > 255:
        raise ValueError(f"unsupported PGM maxval: {max_value}")
    raster = np.frombuffer(data, dtype=np.uint8, count=width * height, offset=i)
    return raster.reshape((height, width)).astype(np.float32)


def load_image(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix == ".pgm":
        return load_pgm(path)

    try:
        import cv2  # type: ignore
    except ImportError:
        cv2 = None
    if cv2 is not None:
        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise FileNotFoundError(f"OpenCV could not read image: {path}")
        return gray.astype(np.float32)

    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "PNG/JPEG require OpenCV (cv2) or Pillow. "
            "Install one of them, or pass a binary .pgm file."
        ) from exc
    with Image.open(path) as img:
        return np.asarray(img.convert("L"), dtype=np.float32)


def maybe_downscale(image: np.ndarray, max_side: int) -> np.ndarray:
    if max_side <= 0:
        return image
    height, width = image.shape
    scale = min(1.0, float(max_side) / float(max(height, width)))
    if scale >= 1.0:
        return image
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    try:
        import cv2  # type: ignore

        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    except ImportError:
        ys = (np.linspace(0, height - 1, new_h)).astype(np.int32)
        xs = (np.linspace(0, width - 1, new_w)).astype(np.int32)
        return image[ys][:, xs].copy()


def affine_warp(image: np.ndarray, degrees: float = 30.0, scale: float = 0.85) -> np.ndarray:
    """Warp like the quality protocol (rotation + uniform scale about center)."""
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise SystemExit("--affine-pair requires OpenCV (cv2) for warpAffine.") from exc
    height, width = image.shape
    center = (width * 0.5, height * 0.5)
    matrix = cv2.getRotationMatrix2D(center, degrees, scale)
    return cv2.warpAffine(
        image, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=0
    ).astype(np.float32)


def extract(image: np.ndarray, backend: str) -> tuple[list, str]:
    height, width = image.shape
    ext = sift_extractor.Extractor(width, height, backend=backend)
    return list(ext.extract(image)), ext.backend


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract and match SIFT features on real image(s)."
    )
    parser.add_argument("image", type=Path, help="First image (.pgm / .png / .jpg)")
    parser.add_argument(
        "image2",
        nargs="?",
        type=Path,
        default=None,
        help="Optional second image; if omitted, warp image1 (30° / 0.85) and match",
    )
    parser.add_argument(
        "--affine-pair",
        action="store_true",
        help="Force affine warp of image1 even if image2 is omitted (default when alone)",
    )
    parser.add_argument(
        "--backend",
        default="auto",
        choices=("auto", "opencl", "sycl"),
        help="Extract backend (default: auto)",
    )
    parser.add_argument(
        "--ratio",
        type=float,
        default=0.8,
        help="Lowe ratio on matcher ambiguity (default: 0.8)",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=1280,
        help="Downscale so max(H,W) <= this (0 disables). Default: 1280",
    )
    args = parser.parse_args()

    if not args.image.is_file():
        print(f"image not found: {args.image}", file=sys.stderr)
        return 2
    if args.image2 is not None and args.affine_pair:
        print("use either image2 or --affine-pair, not both", file=sys.stderr)
        return 2
    if args.image2 is not None and not args.image2.is_file():
        print(f"image not found: {args.image2}", file=sys.stderr)
        return 2

    # Single image ⇒ affine pair so the sample always demonstrates extract+match.
    use_affine = args.affine_pair or args.image2 is None

    print("version:", sift_extractor.__version__)
    print("system_requirements:", sift_extractor.system_requirements())
    print("available_backends:", list(sift_extractor.available_backends()))
    print("has_opencl_matcher:", bool(sift_extractor.has_opencl_matcher))

    image1 = maybe_downscale(load_image(args.image), args.max_side)
    if use_affine:
        image2 = affine_warp(image1)
        pair_desc = f"{args.image} + affine(30deg,0.85)"
    else:
        image2 = maybe_downscale(load_image(args.image2), args.max_side)
        pair_desc = f"{args.image} ↔ {args.image2}"

    h1, w1 = image1.shape
    h2, w2 = image2.shape
    print(f"pair: {pair_desc}")
    print(f"image1 shape={w1}x{h1}  image2 shape={w2}x{h2}")

    print("--- extract ---")
    try:
        feats1, resolved1 = extract(image1, args.backend)
        feats2, resolved2 = extract(image2, args.backend)
    except Exception as exc:  # noqa: BLE001
        print(f"extract FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        f"backend_request={args.backend!r} "
        f"resolved=({resolved1!r},{resolved2!r}) "
        f"features=({len(feats1)},{len(feats2)})"
    )
    if feats1:
        f0 = max(feats1, key=lambda f: float(f["response"]))
        print(
            f"  img1 strongest: x={f0['x']:.2f} y={f0['y']:.2f} "
            f"scale={f0['scale']:.3f} response={f0['response']:.4f}"
        )

    print("--- match ---")
    try:
        matches = list(sift_extractor.match(feats1, feats2, ratio=args.ratio))
    except Exception as exc:  # noqa: BLE001
        print(f"match FAILED: {exc}", file=sys.stderr)
        return 1

    matcher = "opencl" if sift_extractor.has_opencl_matcher else "host"
    print(
        f"matcher={matcher} ratio={args.ratio}: {len(matches)} "
        f"accepted of {len(feats1)} queries"
    )
    for match in matches[:5]:
        q = feats1[int(match["query_index"])]
        print(
            f"  q[{match['query_index']}] ({q['x']:.1f},{q['y']:.1f}) -> "
            f"t[{match['train_index']}] ({match['match_x']:.1f},{match['match_y']:.1f}) "
            f"score={match['score']:.4f} ambiguity={match['ambiguity']:.4f}"
        )
    print(
        f"done: extract features=({len(feats1)},{len(feats2)}) "
        f"+ match accepted={len(matches)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
