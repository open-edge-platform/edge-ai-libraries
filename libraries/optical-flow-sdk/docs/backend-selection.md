<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Backend selection

`Backend::Auto` resolves in this order:

1. SYCL — if `OPTICALFLOW_ENABLE_SYCL=ON` and the toolchain provides `-fsycl`
2. OpenCL — if `OPTICALFLOW_ENABLE_OPENCL=ON`
3. CPU — if `OPTICALFLOW_ENABLE_CPU=ON` (default)

OpenCL DIS is device-resident (pyramid + patch inverse search + densify) when
`OPTICALFLOW_ENABLE_OPENCL=ON`. SYCL still falls back to the CPU DIS path until
kernels land (`icpx` / oneAPI required). Lab gates in `PLAN.md` still gate moat
speed claims (≥10× vs OpenCV CPU DIS-Fast).
