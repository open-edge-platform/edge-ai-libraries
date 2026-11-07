<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Comparison Protocol (OpenCV / OpenCL / SYCL)

Public quality and performance diagnostics for this component compare three arms.
They are **not** algorithm-equivalent; settings and numerical contracts differ.
Do not treat raw speed as improvement until quality eligibility is established
for the intended application.

| Arm | Role |
| --- | --- |
| **OpenCV** | `cv::SIFT` (features2d) diagnostic reference for coverage and geometry |
| **OpenCL** | Intel OpenCL extract + `OpenCLMatcher` GPU matching |
| **SYCL** | SYCL extract + `MatchSiftData` (context-owned extract; process-global legacy reference is not concurrent) |

## Run (Intel GPU hosts)

Configure with SYCL, OpenCL, and the optional OpenCV validation tools:

```bash
cmake -S . -B build -DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release \
  -DSIFT_ENABLE_SYCL=ON -DSIFT_ENABLE_OPENCL=ON \
  -DSIFT_ENABLE_OPENCV_VALIDATION=ON
cmake --build build --parallel --target validate_sift_pair
ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
  build/validate_sift_pair /path/to/image.pgm report.json 10
```

Independent feature exports (no hidden resize; width/height controls rejected):

```bash
build/validate_sift_pair --export-features IMAGE OUTPUT CONFIG opencl|sycl|opencv
```

Record fixture SHA-256, executable/runtime hashes, CPU thread count for OpenCV,
device/driver strings, and the exact option structs for OpenCL and SYCL.

## Timing scope

Include conversion/upload/extraction and owned host outputs. Exclude one-time
context/workspace setup, decode/resize outside the timed path, and matching
unless the experiment is explicitly end-to-end. Prefer fresh processes,
counterbalanced backend order, and enough samples for median/p95. Profiling
modes that force waits are diagnostic only—not acceptance FPS.

## Quality scope

Known-transform or known-homography scoring with a frozen matcher protocol
(ratio test, inlier threshold, precision/RMSE definitions) before interpreting
speed. Feature-count wins alone are not quality acceptance. Held-out viewpoint
corpora remain a separate gate from development fixtures (for example graf).

## Backend selection

See [backend-selection.md](backend-selection.md). `Backend::Auto` is speed-biased
toward SYCL when built; prefer OpenCL explicitly when stability on the current
OpenCL contract matters more than raw Arc throughput.
