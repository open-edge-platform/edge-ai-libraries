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

## Arc Python extract + native vs wrapper (2026-11-03)

Dual `icpx` OpenCL+SYCL+Python install staged to Arc (`labrat`) with the usual
**portable `sycl-runtime`** payload. Arc does **not** ship a system
`/opt/intel/oneapi`/`icpx` install; SYCL Arc work (including prior perf runs)
uses that staged runtime + `ONEAPI_DEVICE_SELECTOR=level_zero:gpu`.

Fixture: historical `input.pgm` 1280×960. Protocol: 3 warmups / 30 samples,
counterbalanced native↔Python order per backend. Module reports
`available_backends=['opencl','sycl']`, Auto→`sycl`.

| Path | OpenCL median ms (2 runs) | SYCL median ms (2 runs) |
| --- | --- | --- |
| Native | 12.07 / 13.46 (mean 12.77) | 10.63 / 10.62 (mean 10.63) |
| Python | 15.23 / 15.14 (mean 15.18) | 12.19 / 12.00 (mean 12.09) |
| Wrapper overhead | ~+19.0% | ~+13.8% |
| Features | 1980 | 3826 |

Feature-count mismatch is expected under unequal backend contracts—not a
quality-parity or CudaSift-floor claim. Python timing includes GIL-released
extract plus list/dict/descriptor materialization. Exploratory within-host
evidence only; not a release soak. Workspace summary:
`results/20261102/arc-python-timing/dual-summary.json`.
