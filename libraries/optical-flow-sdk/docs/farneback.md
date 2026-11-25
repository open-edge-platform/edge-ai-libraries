<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Farneback (CPU + OpenCL)

## What we ship

| Path | Class | Notes |
|------|--------|-------|
| CPU `FarnebackOpticalFlow` / `Algorithm::Farneback` | Separable Farneback poly expansion + UpdateMatrices / box UpdateFlow | OpenCV-aligned layout; soft vs OpenCV identity |
| OpenCL `OpenCLFarnebackOpticalFlow` | Same dial; WLS poly → OpenCV channel order + UpdateMatrices/Flow | `fb_poly_expand` / `fb_update_matrices` / `fb_farneback_update` |

## Poly expansion (landed)

CPU uses OpenCV’s separable Gaussian-moment expansion (`poly_n` / `poly_sigma`)
into 5 channels `[cy, cx, cyy, cxx, cxy]`. OpenCL fits the same quadratic via
per-pixel WLS and stores the same channel order. Displacement follows
Farneback/OpenCV UpdateMatrices (`AᵀA` / `Aᵀb` with current flow folded in) and
winsize box averaging.

Dial (Fast / Medium / Slow):

- `poly_n` = 5 / 5 / 7
- `poly_sigma` = 1.1 / 1.2 / 1.5
- winsize / levels / iterations match usual OpenCV tutorial presets

Expect strong synthetic-shift behavior and tight CPU↔OpenCL parity. Pairwise
EPE vs OpenCV remains a soft honesty gate (pyramid / border details may differ).

DIS + `calc_device` remain the primary ≥10× / quality-report path.

## Hardening

1. Document residual gap vs OpenCV (this file) — **done**
2. Keep `compare_opencv_dis --algo farneback` as the honesty harness
3. Full poly-coefficient expansion — **landed** (CPU + OpenCL)
