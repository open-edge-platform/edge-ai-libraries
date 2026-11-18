#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Dense DIS via OpticalFlow(backend=auto)."""

from __future__ import annotations

import numpy as np
from optical_flow_sdk import OpticalFlow


def main() -> None:
    h, w, dx = 48, 64, 2
    yy, xx = np.mgrid[0:h, 0:w]
    prev = ((xx + yy) % 256).astype(np.uint8)
    next_img = np.zeros_like(prev)
    next_img[:, dx:] = prev[:, :-dx]

    of = OpticalFlow(backend="auto", preset="fast", algorithm="dis")
    flow, _ = of.calc(prev, next_img)
    mag = np.hypot(flow[8:-8, 8:-8, 0], flow[8:-8, 8:-8, 1]).mean()
    print(f"algorithm={of.algorithm} backend={of.backend} mean |flow|={mag:.4f}")


if __name__ == "__main__":
    main()
