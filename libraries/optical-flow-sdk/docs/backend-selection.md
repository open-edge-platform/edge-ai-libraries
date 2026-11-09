<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Backend selection

`Backend::Auto` resolves in this order:

1. OpenCL — if `OPTICALFLOW_ENABLE_OPENCL=ON` (primary GPU latency path)
2. SYCL — if `OPTICALFLOW_ENABLE_SYCL=ON` and the toolchain provides `-fsycl`
3. CPU — if `OPTICALFLOW_ENABLE_CPU=ON` (default)

OpenCL DIS is the primary device path (`calc` host wall, plus `calc_device`
for GPU-resident pipelines). SYCL DIS is a secondary backend (landed; speed
tuning is lower priority than OpenCL). Lab gates in `PLAN.md` target Core
Ultra Series 2 iGPU (≥10× wall vs OpenCV CPU DIS-Fast on **OpenCL**).
