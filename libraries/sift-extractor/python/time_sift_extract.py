#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Matched timing harness for the pybind11 Extractor wrapper."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import numpy as np
import sift_extractor


def make_image(width: int, height: int, seed: int) -> np.ndarray:
    # Match samples/time_sift_extract.cpp pixel formula exactly.
    ys, xs = np.indices((height, width), dtype=np.int32)
    return (32.0 + 40.0 * ((xs * 17 + ys * 13 + seed) % 11)).astype(np.float32)


def load_pgm(path: str) -> np.ndarray:
    data = Path(path).read_bytes()
    if not data.startswith(b"P5"):
        raise ValueError(f"only binary PGM P5 is supported: {path}")
    header_end = 0
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
    while i < len(data) and data[i] in b" \t\r":
        i += 1
    if i < len(data) and data[i] in b"\n":
        i += 1
    header_end = i
    width, height, max_value = values
    if max_value <= 0 or max_value > 255:
        raise ValueError(f"unsupported PGM maxval: {max_value}")
    raster = np.frombuffer(data, dtype=np.uint8, count=width * height, offset=header_end)
    return raster.reshape((height, width)).astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", nargs="?", default="opencl")
    parser.add_argument("width", nargs="?", type=int, default=640)
    parser.add_argument("height", nargs="?", type=int, default=480)
    parser.add_argument("warmups", nargs="?", type=int, default=3)
    parser.add_argument("samples", nargs="?", type=int, default=30)
    parser.add_argument("seed", nargs="?", type=int, default=1)
    parser.add_argument("image", nargs="?", default=None)
    args = parser.parse_args()

    if args.image:
        image = load_pgm(args.image)
        height, width = image.shape
    else:
        width, height = args.width, args.height
        image = make_image(width, height, args.seed)

    extractor = sift_extractor.Extractor(width, height, args.backend)
    features = []
    for _ in range(args.warmups):
        features = extractor.extract(image)

    times_ms: list[float] = []
    for _ in range(args.samples):
        started = time.perf_counter()
        features = extractor.extract(image)
        ended = time.perf_counter()
        times_ms.append((ended - started) * 1000.0)

    median = statistics.median(times_ms)
    mean = statistics.fmean(times_ms)
    print(
        json.dumps(
            {
                "path": "python",
                "backend": extractor.backend,
                "width": width,
                "height": height,
                "warmups": args.warmups,
                "samples": args.samples,
                "seed": args.seed,
                "image": args.image,
                "features": len(features),
                "median_ms": median,
                "mean_ms": mean,
                "fps_median": (1000.0 / median) if median > 0 else 0.0,
                "version": getattr(sift_extractor, "__version__", None),
                "available_backends": list(sift_extractor.available_backends()),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
