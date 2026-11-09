<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Farneback (CPU + OpenCL)

## What we ship

| Path | Class | Notes |
|------|--------|-------|
| CPU `FarnebackOpticalFlow` / `Algorithm::Farneback` | Pyramid + `poly_n` neighborhood gradients + windowed LK | OpenCV-free; soft GT-EPE vs OpenCV in CI |
| OpenCL `OpenCLFarnebackOpticalFlow` | Same poly-n / winsize / levels dial as CPU presets | `fb_poly_lk` in `src/opencl/farneback_kernels.hpp` |

## Poly expansion (landed)

Both CPU and OpenCL use a **polynomial-neighborhood gradient proxy**
(`poly_n` = 5/5/7 for Fast/Medium/Slow) then solve a windowed LK system —
aligned with each other. This is still not OpenCV’s full Farneback polynomial
expansion + `poly_sigma` fit; treat OpenCV pairwise EPE / Fl-all as soft.

Expect:

- Reasonable synthetic-shift / coarse motion behavior
- CPU↔OpenCL parity much tighter than the old central-diff OpenCL path
- **Not** OpenCV numerical identity until a fuller poly / `poly_sigma` port
- DIS + `calc_device` remain the primary ≥10× / quality-report path

## Hardening

1. Document residual gap vs OpenCV (this file) — **done**
2. Keep `compare_opencv_dis --algo farneback` as the honesty harness
3. Optional: full Farneback poly coefficients + `poly_sigma` (or retarget soft
   gates to Farneback-class criteria explicitly)

Do not claim OpenCV Farneback parity until a fuller poly port lands or gates
are explicitly retargeted.
