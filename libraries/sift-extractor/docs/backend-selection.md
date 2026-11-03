<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Backend Selection OPTION (Phase B item 7)

Recorded 2026-11-02. This is the item-7 **OPTION** outcome that enables packaging
and Python follow-ons. It is **not** a CudaSift quality-floor pass or a claim that
OpenCL and SYCL are algorithm-equivalent.

## Decision

**Dual backends with explicit dispatch** (`Backend::OpenCL`, `Backend::Sycl`,
`Backend::Auto`).

Neither backend clears a single-default selection bar on current Arc evidence:

| Evidence | OpenCL | SYCL |
| --- | --- | --- |
| Arc speed (ckpt50 restored, VGA/1080p) | 170 / 56 FPS | 263 / 64 FPS |
| Affine fixture stability | Stable ~401 inliers | Varies ~636–641 |
| Graf viewpoint vs CUDA (smoke, not held-out) | 229 inliers | 302 (CUDA 308) |
| CudaSift quality floor | Unmet | Unmet |
| Repeatability | Better on affine fixture | Unresolved variance |

`Backend::Auto` resolves to SYCL when built, else OpenCL (speed-biased). This is
**not** a quality endorsement. Prefer OpenCL explicitly when stability on the
current OpenCL contract matters more than raw Arc speed.

## Public API

- `sift_extractor/backend.hpp` — enum, availability, `resolve_backend`
- `sift_extractor/opencl_extractor.hpp` — OpenCL owning wrapper
- `sift_extractor/sycl_extractor.hpp` — SYCL owning wrapper
- `sift_extractor/extractor.hpp` — dispatch facade over both
- Options remain **backend-specific** and intentionally unequal

## Follow-ons enabled by this OPTION

Packaging (CMake package + pkg-config + sample), Python bindings, and optional
thin OpenCV type adapters (`SIFT_BUILD_OPENCV_ADAPTER`) may proceed with the
dual-dispatch contract documented above. The OpenCV adapters convert
`cv::Mat`/`cv::KeyPoint` around the core Extractor only; they are not OpenCV
features2d SIFT or Phase D upstream work. Release soak, held-out quality and
REUSE gates remain open.
