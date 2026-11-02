<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Intel GPU Comparison

Compare OpenCL and SYCL on the non-NVIDIA Intel systems using the same binary,
fixture, transform, OpenCV version, matching/scoring code and repetition protocol.
CUDA is a supplemental algorithm reference, not the Intel performance target.

Arc performance is the acceptance target. UHD 770 is a quick correctness and
CPU/GPU regression-check platform only; do not spend tuning effort maximizing its
performance or require Arc/UHD speed ratios to meet a theoretical scaling target.
Preserve UHD correctness and report same-host CPU/GPU results. Where older-GPU
offload is slower or quality is not comparable, retain the README warning rather
than claiming acceleration. Previous-generation integrated GPUs are not recommended
for users requiring a predictable SIFT speed boost. Arc-specific gains take priority.

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

The experimental library context is described in [sycl-context.md](sycl-context.md).
Use the matrix runner's `--sycl-context` option to exercise it across all three
backends; `sycl_lifecycle` labels steady-state timing and context setup/release
are reported separately. The isolated `sycl-context` diagnostic mode omits CPU and
OpenCL and reports only phases exposed by its adapter. Earlier `sycl-reuse`
measurements use the benchmark-local owner and are not automatically results for
the library wrapper.

## CPU/GPU Configuration Matrix

The diagnostic accepts a fifth argument naming a JSON profile:

```bash
ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
  build/validate_sift_pair image.pgm report.json 10 profile.json
python3 scripts/run_comparison_matrix.py build/validate_sift_pair image.pgm results \
  --sizes 640x480 1280x720 1920x1080 --iterations 10
```

Python 3.11+ is required for the matrix runner. The output directory must not
exist. Each case retains its JSON configuration, report and console log; a manifest
records executable/fixture hashes and a CSV summarizes timing and quality. Failed
cases remain visible and make the runner exit nonzero. Resized copies of one
fixture are synthetic workloads, not independent images or newly acquired detail.

| Setting | CPU | OpenCL | SYCL |
| --- | --- | --- | --- |
| nfeatures | OpenCV constructor setting | Response-ranked output cap | Response-ranked output cap |
| nOctaveLayers | Direct | Pyramid intervals | Fixed at 5; not applied |
| contrastThreshold | Direct | Separate openclContrast | Separate syclContrast |
| edgeThreshold | Direct | Hessian ratio `(edge+1)^2/edge` | Not applied |
| sigma | Direct | Base pyramid sigma | Not applied; syclInitBlur is distinct |
| octaves | OpenCV chooses automatically | Direct | Direct |
| cpuThreads | OpenCV worker count | Host conversion may use it | Host conversion may use it |

GPU feature caps happen AFTER extraction and do not limit extraction computation.
Contrast thresholds and scale-space conventions are not equivalent. Profiles vary
one requested control at a time; contrast_low varies separately recorded native
thresholds, not an asserted conversion between them. CPU threads default to 1;
the cpu4 profile measures four workers. Earlier reports used the process default
24 threads and must not be mixed with these single-thread results.

Validated ranges: paired width/height 32-3840/32-2160, nfeatures 0-16000,
nOctaveLayers 1-6, contrastThreshold 0.00001-0.2, edgeThreshold 1-30, sigma 0.5-3,
cpuThreads 1-128, octaves 1-6, native contrast values 0.01-20, syclInitBlur 0.2-3.
Omitting dimensions retains the 640x480 cap; setting both resizes to that exact
shape. Unknown keys, fractional integer settings and out-of-range values fail.

## Centering Repair and Profiling Status

The initial results above precede a SYCL low-pass coordinate repair. The direct
nine-tap horizontal filter read around x-4 but wrote to x, shifting the filtered
image. Correcting its center removed the signed geometry bias on the diagnostic
fixture: mean residual changed from approximately (0.982, 1.580) pixels to
(-0.017, -0.004); inliers increased from about 593 to 639 and RMSE fell from
2.03 to 0.886 pixels. Impulse X/Y centroid assertions now cover this defect;
26 kernel assertions and all 10 registered tests pass on UHD 770.

Corrected single-thread CPU baseline, three warmups and three samples:

| Input Size | CPU Median | SYCL Median | CPU/SYCL Ratio |
| --- | --- | --- | --- |
| 640x480 | 54.91 ms | 12.91 ms | 4.25x |
| 1280x720 | 182.69 ms | 25.24 ms | 7.24x |
| 1920x1080 | 377.86 ms | 45.23 ms | 8.35x |
| 3840x2160 | 1447.48 ms | 136.34 ms | 10.62x |

The 21 size/profile cases plus 4K baseline passed locally. These short-run ratios
are NOT quality-qualified: SYCL still has fewer verified inliers and higher RMSE
than OpenCV. The corrected implementation has not yet been rerun on primary Arc.

Local VTune captures were initially permission-blocked. The user temporarily
enabled perf/ptrace access, allowing GPU-offload and software-hotspot captures with
VTune 2025.8. The original security controls were subsequently restored and verified.
No sampling driver, persistent capability or security configuration was installed.

In the mixed 640x480 diagnostic, ten SYCL extractions produced 70.626 ms aggregate
GPU compute time. Descriptor extraction accounted for 39.664 ms (56.2%), orientation
12.295 ms, extrema 8.174 ms, Laplacian 5.848 ms, low-pass 3.128 ms and downsampling
1.517 ms. These are instrumented task totals, not unprofiled latency estimates.
Descriptor extraction is the strongest measured SYCL kernel optimization target.

The OpenCL path dominated the mixed capture's host costs: clEnqueueReadBuffer
1.795 s over 760 calls, clBuildProgram 0.788 s over 11 calls, and clCreateBuffer
0.173 s over 2420 calls. API durations include waits and can overlap other work;
do not sum them as exclusive costs. The host samples are not sufficient to blame
SYCL allocations specifically. Isolate that workload before changing allocation
or synchronization strategy. No GPU hardware counters were collected and several
dependencies lacked debug symbols, so no TOPS utilization or stall diagnosis is
supported. The centering change remains a correctness repair, not a performance
optimization. The subsequent local descriptor experiment is recorded below.

## Isolated SYCL Experiment

The optional sixth argument `sycl-only` skips OpenCL and CPU extraction/scoring:

```bash
ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
  build/validate_sift_pair image.pgm isolated.json 30 profile.json sycl-only
```

The report includes raw end-to-end samples, quality on the transformed pair, and
conversion, image-allocation/upload, feature/scratch-allocation, extract/wait,
host-descriptor and cleanup timings. Stages are wall-clock measurements, not GPU
event timings, and medians are not additive. Internal allocations/prefiltering/
copies inside ExtractSift remain in extract_and_wait; cleanup excludes later
destruction of the returned feature vectors. Reference logging remains included.

On the local UHD 770, a 15-sample baseline measured 13.36 ms end to end and
12.90 ms extract/wait; outer feature/scratch allocation was 0.034 ms. This does
not support outer allocation reuse as the first target, nor rule out internal
allocation overhead.

The descriptor experiment uses four local histogram banks, assigning each set of
32 work-items a bank, then merges before unchanged normalization. This increases
local histogram storage from 512 to 2048 bytes and adds merge barriers. Reduced
atomic contention is the hypothesis; hardware counters were not collected.

Sequential A/B/B/A runs with three warmups and 30 measured frames per run:

| UHD 770 Workload | Baseline Pooled Median | Banked Pooled Median | Latency Reduction |
| --- | --- | --- | --- |
| 640x480 | 13.20 ms | 12.56 ms | 4.8% |
| 1920x1080 | 46.14 ms | 45.06 ms | 2.3% |

Both rounds at each size favor the candidate. VGA quality matches; 1080p shows
small variation also present between baseline rounds. All 10 tests and 21 matrix
executions plus the additional 4K baseline pass. Against the corrected 21-case
matrix baseline, maximum relative inlier
change is below 0.5% and maximum absolute RMSE change is 0.0042 px. These are local
short-run observations on resized copies of one image, not a held-out quality gate,
cross-GPU validation, proven contention reduction or general speedup guarantee.
The primary Arc outcome is recorded below; broader quality eligibility remains
outstanding.

## Primary Arc Validation

The exact preserved baseline/candidate binaries were checksum-verified and tested
on primary Arc with the same VGA/1080p profiles, three warmups and 30 measured
frames per A/B/B/A run. All three SYCL smoke programs pass, including the 26 kernel
assertions and low-pass centroid regression. The corrected image probe has about
638-640 inliers/RMSE 0.885px, confirming the centering repair on this second GPU.

| Arc Workload | Baseline Pooled Median | Banked Pooled Median | Latency Reduction |
| --- | --- | --- | --- |
| 640x480 | 7.2476 ms | 7.1755 ms | 0.99% |
| 1920x1080 | 27.0342 ms | 26.7535 ms | 1.04% |

This is only a small observed gain, not evidence of a robust portable improvement.
Run-to-run drift and quality variation remain. The banked kernel remains an
experimental candidate, with no stronger claim than the recorded local results.

Unlike UHD 770, Arc outer feature/scratch allocation takes about 3.48ms at VGA and
12.4-12.8ms at 1080p, versus extraction/wait around 3.3ms and 11.4-11.8ms. Phase
medians are not additive, but this identifies allocation lifecycle as a meaningful
primary-host optimization target. Next experiment: reuse per-extractor feature and
scratch buffers across frames, report cold versus warm lifecycle separately, and
verify unchanged quality before claiming a benefit. The CPU timing and broad SIFT
quality gates remain separate requirements.

## Workspace Lifecycle Experiment

The optional `sycl-reuse` mode retains feature and scratch allocations for a fixed
image shape and octave count, using the existing SYCL API's caller-owned buffers:

```bash
ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
  build/validate_sift_pair image.pgm reuse.json 30 profile.json sycl-reuse
```

`sycl-only` remains the per-call allocation baseline. Both modes use the same
binary and kernel implementation. Reuse does not retain the image buffer or remove
image upload, extraction, descriptor validation/copying or reference logging from
steady-state timing. It excludes one-time feature/scratch setup and final release,
which are reported separately. `first_workspace_frame_ms` includes the first
allocation and frame but excludes process/queue initialization and follows the
per-call correctness reference; it is NOT full application cold-start time.

Reuse quality is scored against the per-call pair, and blank-then-textured frames
are checked outside the timed interval for stale features. A workspace rejects a
shape or octave-count change; create a new workspace for a different configuration.
The owner is noncopyable. This is diagnostic lifecycle evidence, not a reentrant
public application context; the legacy global queue/kernel state remains.

Local UHD 770 correctness and all 10 tests pass. Primary Arc A/B/B/A validation
completed with the same executable for both modes, three warmups and 30 measured
frames per run:

| Arc Input | Per-call Pooled Median | Reused Steady-state Median | Latency Reduction |
| --- | --- | --- | --- |
| 640x480 | 7.1624 ms | 3.6900 ms | 48.5% |
| 1920x1080 | 25.9284 ms | 15.1097 ms | 41.7% |

These are lifecycle improvements against per-frame GPU allocation, not kernel or
CPU/GPU speedups. First-workspace-frame costs were 7.79-7.90ms at VGA and
26.46-26.77ms at 1080p; final workspace release was about 0.011-0.013ms. One-time
costs are not included in the steady-state medians. Process and queue startup
were already warm and are not represented by first_workspace_frame_ms.

Feature counts match (1366/1188 at VGA, 4939/4071 at 1080p), and blank-to-textured
reuse checks pass. Within the reuse runs, VGA RMSE remains near 0.885px and 1080p
near 0.905px; inlier variation versus same-run per-call quality is small. This is
not a held-out noninferiority test or OpenCV equivalence. The verified benefit is
on the primary Arc host; public context ownership, concurrency safety, full Arc
CPU/OpenCL/SYCL matrix and broader image/configuration coverage remain outstanding.