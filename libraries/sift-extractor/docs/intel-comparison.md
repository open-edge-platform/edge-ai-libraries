<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Intel GPU Comparison

Compare OpenCL and SYCL on the non-NVIDIA Intel systems using the same binary,
fixture, transform, OpenCV version, matching/scoring code and repetition protocol.
CUDA is a supplemental algorithm reference, not the Intel performance target.

## Run

Configure with SIFT_ENABLE_SYCL=ON, SIFT_ENABLE_OPENCL=ON,
SIFT_ENABLE_OPENCV_VALIDATION=ON and the icpx compiler. Then:

```bash
ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
  build/validate_sift_pair /path/to/image.pgm report.json 10
```

The SYCL queue must select an Intel GPU. The OpenCL prototype selects the first
GPU on an Intel platform; use single-Intel-GPU hosts for this protocol. Multiple
Intel GPUs need explicit per-context device selection before claiming co-location.
The JSON records quality, device/driver, parameters and timing samples. Source
fixture SHA256 and executable/runtime hashes belong in the run receipt.

Input is capped to 640x480, then rotated 30 degrees and scaled by 0.85. CPU
BFMatcher uses L2, a 0.8 ratio threshold and a 3-pixel known-transform inlier limit.
OpenCL and SYCL extraction parameters are NOT equivalent. Their quality eligibility
must be established before choosing a backend or interpreting speed as improvement.

## Timing Scope

Three warmup extractions per backend precede 1-100 measured repetitions. Backend
order rotates across OpenCL, SYCL and the OpenCV CPU baseline. The reported
median/min/max and raw samples include float
conversion, allocation, per-call setup, transfers, extraction, host descriptors
and reference console logging. File loading, transform generation, matching,
and initial GPU detector construction are excluded. OpenCV CPU extraction is timed
separately, with CPU thread count and optimized-code status recorded. CPU/GPU
latency ratios are diagnostic until quality eligibility is established; OpenCV
CPU SIFT is already optimized, not a naive implementation.
Feature counts must remain stable throughout the repetitions. Device operations
are completed before timing ends. This is diagnostic application-visible latency,
not pure kernel time or a release performance gate.

## Hardware Interpretation

Record advertised GPU TOPS with the vendor source, precision, dense/sparse mode
and relevant execution unit. Never substitute platform-total or NPU TOPS for GPU
TOPS. SIFT is predominantly FP32 scalar/vector work; INT8 or matrix-unit TOPS are
not a denominator for its utilization unless the implementation actually uses
those operations. Unknown specifications remain unknown, not inferred from names.

For eligible runs, report latency and images/second first. Compare measured
cross-GPU speedup with verified FP32-throughput and memory-bandwidth ratios,
accounting for allocations, host work, transfers, power/clock limits and architecture.
Compute-unit count and maximum clock are metadata, not interchangeable hardware
units or measured throughput. A roofline comparison needs estimated/measured work
and bytes, not just a marketing TOPS ratio. An optimization claim additionally
requires before/after runs on the same GPU at accepted quality.

## Initial Diagnostic Results

One 640x480 transformed fixture, identical comparison executable and OpenCV 4.10.0,
three warmups and ten measured extractions per backend:

| Intel GPU | OpenCL Median | SYCL Median | OpenCL Inliers / RMSE | SYCL Inliers / RMSE |
| --- | --- | --- | --- | --- |
| UHD Graphics 770 | 218.00 ms | 11.99 ms | 263 / 0.359 px | 594 / 2.025 px |
| Arc Graphics | 130.14 ms | 11.42 ms | 263 / 0.359 px | 586 / 2.028 px |

Arc/UHD end-to-end speedup is 1.68x for OpenCL and 1.05x for SYCL. OpenCL quality
is identical in these reports; SYCL matches differ slightly despite equal feature
counts. These are single-run diagnostic observations, not an accepted accuracy,
determinism or scaling gate. Backend quality differs substantially, and parameters
are unequal. Do not select a winner from latency alone.

The Arc SYCL extraction-stage console timer is faster than UHD, but that timer
does not cover the same scope as the end-to-end report. Allocation, transfer,
host conversion, descriptor handling and cleanup must be measured separately
before attributing the weak end-to-end scaling to a specific cause. Vendor GPU
TOPS/FP32/bandwidth specifications are not yet verified, so no utilization or
TOPS-normalized efficiency is claimed. Secondary-host validation remains pending.

## Portable Staging

The existing stage_opencl_host.sh supports SIFT_STAGE_PAIR_IMAGE together with
SIFT_STAGE_SYCL_BUILD and SIFT_STAGE_OPENCV_PREFIX. The latter must contain a lean
OpenCV installation and share/licenses/opencv4 notices. The optional bundle adds
the comparison executable, original fixture, dependent OpenCV libraries and
notices to the SHA256 manifest. With --test it runs the Intel GPU smoke tests,
then writes intel-comparison.json with ten measured repetitions. Use the already
verified matching private Level Zero loader/tracing pair for the target runtime.
No system compiler, OpenCV installation, driver or power-setting changes are needed.