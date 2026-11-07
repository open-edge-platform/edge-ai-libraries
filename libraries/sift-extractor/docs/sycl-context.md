<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# SYCL Context

`sift_extractor::SyclExtractor` is an OpenCV-free owning wrapper around the SYCL
reference extractor. It retains image, feature, scratch, and upload buffers for
repeated fixed-size frames. Prefer `Extractor` with `Backend::Sycl` or
`Backend::Auto` when you want backend dispatch; use `SyclExtractor` when you
need direct ownership of the SYCL path.

## Consume

Build with SIFT_ENABLE_SYCL=ON and icpx. Install the component and link the exported
target from a C++17 application using the compatible SYCL compiler/runtime:

```cmake
find_package(sift_extractor CONFIG REQUIRED)
target_link_libraries(my_application PRIVATE sift_extractor::sift_sycl_extractor)
```

```cpp
#include <sift_extractor/sycl_extractor.hpp>
#include <vector>

sift_extractor::SyclExtractorOptions options;
options.octaves = 4;
options.capacity = 32768;
options.initial_blur = 1.0;
options.contrast_threshold = 3.0f;
sift_extractor::SyclExtractor extractor(1920, 1080, options);
std::vector<float> grayscale(1920 * 1080, 0.0f);
auto features = extractor.extract(grayscale.data(), grayscale.size());
```

Reuse the extractor for subsequent frames. Returned vectors own keypoint and
128-float descriptor storage independently of the extractor and future calls.
No OpenCV or legacy SYCL headers are needed by the public header.

## Contract and Bounds

Input is host grayscale FP32, normally using 0-255 image intensity units with
the native threshold. Element count and row stride are in FLOAT ELEMENTS, not
bytes. A zero stride means tightly packed rows. Input must remain valid during
the synchronous call; the context copies the active pixels into owned upload
storage. Padding is not interpreted as image content.

Width is 32-3840, height 32-2160, octaves 1-6, with at least 8 pixels in each
dimension at the smallest octave. Capacity is 1-262144, initial blur is finite
and positive up to 3, and contrast threshold is finite and positive. Dimensions
and options are fixed at construction; create another context to change them.
Null/short/nonfinite inputs, short or overflowing strides and invalid options
are rejected. Capacity saturation fails visibly instead of silently reporting
truncated output. The wrapper validates finite keypoints and nonzero finite
descriptors; it does not certify reference-equivalent descriptor normalization.

Construction allocates retained buffers and is NOT part of steady-state timing.
Destruction releases them. The diagnostic `sycl-context` mode reports first-frame
setup and release separately. The matrix runner's `--sycl-context` uses this
library path and records setup/release alongside steady-state CPU/GPU timings.

## Concurrency and Runtime Limits

Contexts are noncopyable and nonmovable. All wrapper construction, extraction and
destruction is serialized through a process-wide mutex because the legacy queue
and device-kernel configuration remain global. Multiple wrapper callers therefore
serialize rather than execute independently on the GPU. Do NOT interleave raw
SiftData/GetSyclQueue APIs concurrently with wrapper operations; those APIs bypass
the mutex. Caller code must still protect object lifetime during concurrent calls.

Only Intel GPU execution is accepted; no automatic CPU fallback is provided.
Asynchronous SYCL failures now propagate through explicit wait_and_throw boundaries
instead of being logged and swallowed. A controlled host-task failure regression
checks this behavior without invalid device access. Queue lifetime, global buffer
teardown and recovery after device loss remain outstanding hardening work. No
concurrency-performance, arbitrary-device recovery or production-readiness
guarantee is made.

## Validation Status

Local UHD 770 tests cover repeated textured/blank frames, padded input, invalid
buffers/stride/NaN, independent output lifetime, interleaved contexts with different
blur settings and two serialized host-thread calls. An installed consumer builds
and runs using only the public header/exported target and no OpenCV dependency.
The context-backed full matrix now passes on primary Arc: 21 cases across VGA,
720p and 1080p plus a 4K baseline, each with three warmups and three samples.
Context regression also passes on Arc, including input checks, padded rows,
interleaved settings, serialized host threads, output lifetime and saturation.

| Baseline Input | Single-thread CPU | OpenCL | SYCL Context Steady State |
| --- | --- | --- | --- |
| 640x480 | 61.16 ms | 136.62 ms | 5.12 ms |
| 1280x720 | 139.97 ms | 185.92 ms | 9.76 ms |
| 1920x1080 | 294.48 ms | 265.39 ms | 17.79 ms |
| 3840x2160 | 1107.90 ms | 948.33 ms | 41.69 ms |

The raw CPU/SYCL ratios are approximately 12.0x, 14.3x, 16.5x and 26.6x, but are
NOT accepted equivalent-output speedups. Baseline 1080p inliers/RMSE are CPU
4092/0.351px versus SYCL 2096/0.903px, and parameters are not equivalent. Earlier
isolated workspace A/B runs and these mixed-backend diagnostics have different
execution contexts and should not be used as paired evidence of wrapper overhead.
Raw per-case JSON records context setup/release separately. Additional corpus,
configuration and runtime-error hardening remain outstanding.