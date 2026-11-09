<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Farneback (CPU + OpenCL)

## What we ship

| Path | Class | Notes |
|------|--------|-------|
| CPU `FarnebackOpticalFlow` / `Algorithm::Farneback` | Pyramid + `poly_n` / `poly_sigma` neighborhood gradients + windowed LK | OpenCV-free; soft GT-EPE vs OpenCV in CI |
| OpenCL `OpenCLFarnebackOpticalFlow` | Same `poly_n` / `poly_sigma` / winsize / levels dial as CPU | `fb_poly_lk` in `src/opencl/farneback_kernels.hpp` |

## Poly dial (landed)

Both CPU and OpenCL use a **polynomial-neighborhood gradient proxy**:

- `poly_n` = 5/5/7 for Fast/Medium/Slow (neighborhood diameter)
- `poly_sigma` = 1.1/1.2/1.5 (Gaussian σ for that neighborhood, OpenCV dial)

Weights are `exp(-0.5 · r² / poly_sigma²)`, then a windowed LK solve. This is
still not OpenCV’s full Farneback polynomial-coefficient expansion; treat
OpenCV pairwise EPE / Fl-all as soft.

Expect:

- Reasonable synthetic-shift / coarse motion behavior
- Tight CPU↔OpenCL parity when presets match
- **Not** OpenCV numerical identity without a fuller poly-coefficient port
- DIS + `calc_device` remain the primary ≥10× / quality-report path

## Hardening

1. Document residual gap vs OpenCV (this file) — **done**
2. Keep `compare_opencv_dis --algo farneback` as the honesty harness
3. Optional: full Farneback poly coefficients (or retarget soft gates to
   Farneback-class criteria explicitly)

Do not claim OpenCV Farneback parity until a fuller poly-coefficient port
lands or gates are explicitly retargeted.
