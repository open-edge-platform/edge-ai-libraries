<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Backend selection

`Backend::Auto` resolves in this order:

1. SYCL — if `OPTICALFLOW_ENABLE_SYCL=ON` and the toolchain provides `-fsycl`
2. OpenCL — if `OPTICALFLOW_ENABLE_OPENCL=ON`
3. CPU — if `OPTICALFLOW_ENABLE_CPU=ON` (default)

Until device DIS kernels land, SYCL and OpenCL backends fall back to the CPU
DIS path so API and packaging stay wired. Lab gates in `PLAN.md` still require
real GPU kernels before moat speed claims.
