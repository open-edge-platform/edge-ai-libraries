# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Generate (or optionally download) a small sample image set for exercising the
encoder/decoder REST pipeline end-to-end.

Default mode is fully offline and deterministic: synthetic JPEGs with a handful
of colored rectangles are generated locally with PIL, so `tests/` never needs to
ship or fetch large binary datasets. Pass --source picsum to instead download a
few real placeholder photos from https://picsum.photos (requires network).

Usage:
    python tests/sample_data/fetch_sample_data.py
    python tests/sample_data/fetch_sample_data.py --count 20 --source picsum
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "images"
DEFAULT_COUNT = 10
DEFAULT_SIZE = (640, 480)


def _synthetic_image(index: int, size: tuple[int, int], seed: int) -> Image.Image:
    rng = random.Random(seed + index)  # nosec B311 - synthetic test image generation, not security/crypto related
    width, height = size
    img = Image.new(
        "RGB", size, color=(rng.randrange(30, 90), rng.randrange(30, 90), rng.randrange(60, 120))
    )
    draw = ImageDraw.Draw(img)
    for _ in range(rng.randrange(2, 6)):
        x1 = rng.randrange(0, max(1, width - 20))
        y1 = rng.randrange(0, max(1, height - 20))
        x2 = min(width, x1 + rng.randrange(20, max(21, width // 3)))
        y2 = min(height, y1 + rng.randrange(20, max(21, height // 3)))
        color = (rng.randrange(120, 255), rng.randrange(120, 255), rng.randrange(120, 255))
        draw.rectangle([x1, y1, x2, y2], fill=color)
    return img


def generate_synthetic(output_dir: Path, count: int, size: tuple[int, int], seed: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(1, count + 1):
        img = _synthetic_image(i, size, seed)
        path = output_dir / f"sample_{i:03d}.jpeg"
        img.save(path, format="JPEG", quality=90)
        paths.append(path)
    return paths


def download_picsum(output_dir: Path, count: int, size: tuple[int, int]) -> list[Path]:
    import httpx

    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = size
    paths = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for i in range(1, count + 1):
            resp = client.get(f"https://picsum.photos/seed/star-image-{i}/{width}/{height}")
            resp.raise_for_status()
            path = output_dir / f"sample_{i:03d}.jpeg"
            path.write_bytes(resp.content)
            paths.append(path)
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--width", type=int, default=DEFAULT_SIZE[0])
    parser.add_argument("--height", type=int, default=DEFAULT_SIZE[1])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--source",
        choices=["synthetic", "picsum"],
        default="synthetic",
        help="synthetic (default, offline, deterministic) or picsum (downloads real placeholder "
             "photos, needs network access)",
    )
    args = parser.parse_args(argv)

    size = (args.width, args.height)
    if args.source == "synthetic":
        paths = generate_synthetic(args.output_dir, args.count, size, args.seed)
    else:
        paths = download_picsum(args.output_dir, args.count, size)

    print(f"Wrote {len(paths)} sample images to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
