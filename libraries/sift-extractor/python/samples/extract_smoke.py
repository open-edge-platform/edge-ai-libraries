#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Smoke sample: import wheel-installed sift_extractor and run extract."""

from __future__ import annotations

import sys

import numpy as np
import sift_extractor


def main() -> int:
    print("version:", sift_extractor.__version__)
    print("system_requirements:", sift_extractor.system_requirements())
    print("available_backends:", list(sift_extractor.available_backends()))

    width, height = 640, 480
    # Textured synthetic scene so OpenCL/SYCL return non-zero features.
    rng = np.random.default_rng(0)
    image = np.full((height, width), 40.0, dtype=np.float32)
    for _ in range(40):
        cy = int(rng.integers(40, height - 40))
        cx = int(rng.integers(40, width - 40))
        yy, xx = np.ogrid[-30:31, -30:31]
        mask = xx * xx + yy * yy <= 25 * 25
        image[cy - 30 : cy + 31, cx - 30 : cx + 31][mask] = 200.0
    image = np.clip(image + rng.normal(0, 3.0, image.shape), 0, 255).astype(np.float32)

    for backend in ("auto", "opencl", "sycl"):
        try:
            ext = sift_extractor.Extractor(width, height, backend=backend)
            features = ext.extract(image)
            print(
                f"backend_request={backend!r} resolved={ext.backend!r} "
                f"features={len(features)}"
            )
            if features:
                f0 = features[0]
                print(
                    f"  first: x={f0['x']:.2f} y={f0['y']:.2f} "
                    f"scale={f0['scale']:.3f} desc_dim={len(f0['descriptor'])}"
                )
        except Exception as exc:  # noqa: BLE001 - sample should show backend failures
            print(f"backend_request={backend!r} FAILED: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
