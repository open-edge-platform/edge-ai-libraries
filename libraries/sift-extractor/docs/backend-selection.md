<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Backend Selection (dual OpenCL + SYCL)

Recorded decision: keep **dual backends with explicit dispatch**
(`Backend::OpenCL`, `Backend::Sycl`, `Backend::Auto`). This enables packaging and
Python. It is **not** a claim that OpenCL and SYCL are algorithm-equivalent, and
it is **not** a quality pass against OpenCV. See [comparison.md](comparison.md)
and [quality.md](quality.md).

## Decision summary

Neither backend clears a single-default selection bar on current Arc evidence:

| Evidence | OpenCL | SYCL |
| --- | --- | --- |
| Arc speed (exploratory VGA/1080p extract) | ~170 / ~56 FPS | ~263 / ~64 FPS |
| Affine fixture stability | Stable inlier counts | Varies across repeats |
| Viewpoint smoke vs OpenCV (dev fixtures) | Trails OpenCV coverage | Closer on some views; still unequal contracts |
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

## Packaging and soak

CMake package, pkg-config, samples, optional Python, and optional OpenCV type
adapters are available. Root README lists this component under Computer Vision
Primitives. Scoped CI discloses absent GPU runners. Exploratory and `--release`
(10k mixed calls) soak harnesses exist; held-out quality and REUSE publication
gates remain open.

## Arc Python extract + native vs wrapper (exploratory)

Dual OpenCL+SYCL+Python on Arc (portable SYCL runtime when the host has no system
oneAPI). Fixture 1280×960; 3 warmups / 30 samples; Auto→`sycl`.

| Path | OpenCL median ms | SYCL median ms |
| --- | --- | --- |
| Native | ~12.8 | ~10.6 |
| Python | ~15.2 | ~12.1 |
| Features | 1980 | 3826 |

Feature-count mismatch is expected under unequal contracts—not OpenCV parity.
Python timing includes GIL-released extract plus materialization. Exploratory
only; not a release soak.
