<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Farneback (CPU + OpenCL)

## What we ship

| Path | Class | Notes |
|------|--------|-------|
| CPU `FarnebackOpticalFlow` / `Algorithm::Farneback` | Farneback-style pyramid + neighborhood motion | OpenCV-free; soft GT-EPE vs OpenCV in CI |
| OpenCL `OpenCLFarnebackOpticalFlow` | **Farneback-class** dense windowed LK on a pyramid | Same level/winsize/iter dial as CPU presets |

## Why OpenCL is “soft” vs OpenCV

OpenCV `calcOpticalFlowFarneback` uses **polynomial expansion** (`poly_n` /
`poly_sigma`) then solves for displacement. Our OpenCL port uses **central-diff
gradients + windowed Lucas–Kanade** at each pyramid level (`fb_windowed_lk` in
`src/opencl/farneback_kernels.hpp`) — a lighter first device path, not a
bit-exact Farneback clone.

Expect:

- Reasonable synthetic-shift / coarse motion behavior
- **Not** OpenCV numerical identity (pairwise EPE / Fl-all will look soft)
- DIS + `calc_device` remain the primary ≥10× / quality-report path; Farneback
  OpenCL is a secondary classical option

## Hardening plan (P3)

1. Document residual gap (this file) — **done**
2. Keep `compare_opencv_dis --algo farneback` as the honesty harness
3. Optional follow-on: poly-expansion kernels (or accept “Farneback-class”
   naming permanently and tighten soft GT-EPE gates only)

Do not claim OpenCV Farneback parity until poly expansion lands or gates are
explicitly retargeted to Farneback-class criteria.
