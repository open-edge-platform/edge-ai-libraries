<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Quality Diagnostic Status

Quality work for redistribution compares **OpenCV**, **OpenCL**, and **SYCL**
under a frozen matcher/geometry protocol. See [comparison.md](comparison.md).

## Current posture

- OpenCL and SYCL retain **unequal** option contracts (octaves, thresholds,
  capacity, scale-up). Feature counts and inlier totals are not directly
  comparable without documenting those differences.
- On development affine fixtures, OpenCL has been more stable across repeats;
  SYCL has been faster on Arc but can vary inlier/feature counts across
  identical processes. Neither backend is declared application-ready quality.
- OpenCV `cv::SIFT` remains a diagnostic coverage/geometry reference, not a
  drop-in numerical twin of either GPU backend.
- Held-out known-homography corpora and full REUSE publication gates remain
  open. Graf and other development views are not held-out acceptance.

## What not to claim

- Do not claim OpenCL/SYCL parity with each other or with OpenCV from raw
  inlier or FPS tables alone.
- Do not publish acceptance FPS from profiled runs that force extra waits.
- Synthetic and resized development fixtures are not held-out viewpoint proof.
