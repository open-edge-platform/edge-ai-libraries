<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Backend selection

`Backend::Auto` resolves in this order:

1. SYCL — if `OPTICALFLOW_ENABLE_SYCL=ON` and the toolchain provides `-fsycl`
2. OpenCL — if `OPTICALFLOW_ENABLE_OPENCL=ON`
3. CPU — if `OPTICALFLOW_ENABLE_CPU=ON` (default)

OpenCL and SYCL DIS are device-resident (pyramid + patch inverse search +
atomic densify) when their CMake options are ON. SYCL builds need `icpx` /
oneAPI (`-fsycl`). Lab gates in `PLAN.md` target Core Ultra Series 2 iGPU
(≥10× wall vs OpenCV CPU DIS-Fast).
