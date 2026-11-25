#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Sparse PyrLK via SparsePyrLK(backend=auto)."""

from __future__ import annotations

import numpy as np
from optical_flow_sdk import SparsePyrLK, SparsePyrLKOptions


def main() -> None:
    h, w, dx, dy = 120, 160, 4, -1
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    prev = (128.0 + 55.0 * np.sin(0.2 * xx) * np.cos(0.15 * yy)).clip(0, 255).astype(np.uint8)
    next_img = np.zeros_like(prev)
    for y in range(h):
        for x in range(w):
            sx, sy = x - dx, y - dy
            if 0 <= sx < w and 0 <= sy < h:
                next_img[y, x] = prev[sy, sx]

    opts = SparsePyrLKOptions()
    opts.max_level = 2
    opts.win_size = 15
    lk = SparsePyrLK(opts, backend="auto")
    pts = np.array([[40.0, 40.0], [80.0, 60.0], [120.0, 90.0]], dtype=np.float32)
    tracked, status, err = lk.calc(prev, next_img, pts)
    print(f"backend={lk.backend}")
    for i, (p, t, s, e) in enumerate(zip(pts, tracked, status, err)):
        print(
            f"pt{i} ({p[0]:.0f},{p[1]:.0f}) -> ({t[0]:.3f},{t[1]:.3f}) "
            f"status={int(s)} err={float(e):.5f}"
        )


if __name__ == "__main__":
    main()
