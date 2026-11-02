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

### OpenCL Program Reuse Experiment

The OpenCL detector now lazily retains its Gaussian-pyramid owner across image
calls, avoiding repeated Gaussian program construction on a retained extractor.
Pyramid pixels still round-trip through host storage; stage buffers and feature
kernels still allocate per call. This is not a GPU-resident pipeline yet.
Repeated textured/blank/resized/reconfigured frame tests preserve feature positions,
scales, orientations and descriptors exactly. All ten local regression tests pass.
An Arc same-settings A/B/B/A experiment is prepared, but authentication closed at
the first SSH attempt. The retry completed on primary Arc with ten samples per
case and all regression checks passing. A/B/B/A pooled medians were VGA
134.395ms baseline vs 132.561ms retained (1.36% lower), and 1080p 263.891ms vs
264.352ms (0.17% higher). Treat this as no demonstrated performance gain; the
VGA difference is small and inconsistent across sizes. OpenCL quality was
unchanged at 263 inliers/0.359px RMSE for VGA and 1300/0.430px for 1080p. Receipt
and raw results: `results/20261101/arc-opencl-program-reuse.sh` and Arc stage
`~/.local/share/sift-extractor-staging/arc-opencl-program-1a545c66495a1f37`.

### complete-gpu-sift Arc Baseline

On primary Arc, the requested reference measured median detection-only throughput
of 168.875 FPS (5.92ms/image) at VGA and 54.995 FPS (18.18ms/image) at 1080p,
across ten independent process runs. This does not reproduce the README's 1,461
FPS claim. The temporary benchmark copy only changes Intel GPU platform selection,
skips untimed visualization output, and permits skipping matching; the original and
benchmark source snapshots and hashes are preserved in Arc stage
`~/.local/share/sift-extractor-staging/complete-gpu-baseline-2a52c9ece8727c38-run2`.

This is a raw throughput target, not quality-equivalent SIFT. The reference uses
three full-resolution Gaussian images and one DoG plane; it does not perform a
multi-octave pyramid, subpixel refinement or dominant orientation assignment.
Its descriptor path and fixed keypoint cap also differ. The current diagnostic
starts from grayscale input while the reference uploads color and converts it on
device. Current OpenCL baseline medians were 127.325ms VGA and 303.539ms 1080p
(21.5x and 16.7x slower than the reference). Retained stage-buffer experiment
measured 139.565ms VGA and 235.434ms 1080p (23.6x slower at VGA, 12.9x at 1080p);
inlier counts/RMSE were unchanged. Buffer reuse improves 1080p by 22.4% but
regresses VGA by 9.6%; neither case meets the measured raw throughput target.

### Shared Gradient Experiment

Orientation and descriptor kernels now share a per-level magnitude/orientation
precompute, avoiding repeated finite differences, `hypot`, and `atan2` for every
keypoint's overlapping support window. Against the feature-kernel-cache build, a
30-sample Arc A/B/B/A measured pooled medians of VGA 134.091ms before and
117.443ms after; 1080p 265.677ms before and 243.370ms after. Pooled median latency
improved 12.4% at VGA and 8.4% at 1080p with the cache-validity guard and corrected
read-write gradient buffers included. OpenCL
quality remained 263 inliers/0.359px RMSE at VGA and 1300/0.430px at 1080p.
Receipt and raw data: `results/20261101/arc-opencl-shared-gradients.sh` and Arc
stage `~/.local/share/sift-extractor-staging/arc-opencl-gradients-8ae394c57953198b`.
Latency remains about 19.8x and 13.4x higher than complete-gpu-sift at VGA and
1080p, and quality compatibility is not established.

### OpenCL Feature Budget

The comparison now passes `nfeatures` into OpenCL extraction and prunes the
response-ranked scale-space list before orientation and descriptors, while
preserving the adapter's final response-ranked output cap. The exact top-feature
regression passes. On Arc, a 30-sample A/B/B/A at `nfeatures=500` versus the prior
post-extraction cap measured pooled medians of VGA 114.335/113.946ms (0.3% lower)
and 1080p 244.694/236.862ms (3.2% lower). This is a small observed gain, not a
route to the reference rate. The cap itself changes quality relative to unlimited
features: inliers/RMSE are 226/0.341px at VGA and 261/0.458px at 1080p, versus
263/0.359px and 1300/0.430px. Metrics were unchanged between the old and new cap
implementations. Treat feature budgets as an explicit quality/performance option,
not equivalent extraction. Receipt and raw
results: `results/20261101/arc-opencl-feature-cap.sh` and Arc stage
`~/.local/share/sift-extractor-staging/arc-opencl-feature-cap-8144074012742c96-retry2`.

Next measure and remove remaining transfer/allocation overhead and optimize
descriptor work as indicated by Arc stage timings. No OpenCL optimization ceiling
or quality parity is claimed. Profile runner: `results/20261101/arc-opencl-stage-profile.sh`.

### Device-Resident Pyramid Construction

The OpenCL extractor now shares its retained in-order queue/context with Gaussian
processing. A combined Gaussian/DoG builder uploads the image once, chains blur,
downsample and difference kernels through reusable read-write device buffers, and
downloads the completed levels in one terminal batch. Gaussian coefficients are
cached by value. Buffer capacity grows as needed and is retained until owner
destruction; peak device memory is higher because all pyramid levels coexist.
Readbacks complete before returning, including when a later enqueue fails.

This is device residency **within pyramid construction**, not a fully resident
extractor. All Gaussian/DoG levels still return to host vectors, and detection,
refinement and gradient preparation still upload their inputs. Existing standalone
host primitives remain available as an independent comparison path. The pyramid
regression requires exact pixel and metadata equality across odd/tiny dimensions,
changed input, octave/layer/sigma changes, blank frames and subsequent reuse.
The full local suite passes 10/10; UHD results are correctness evidence only.

With `SIFT_OPENCL_PROFILE`, `gaussian_dog_ms` replaces the separate `gaussian_ms`
and `dog_ms` fields because the kernels are interleaved. It includes construction,
transfers, allocation and synchronization, not isolated kernel time.

Arc validation completed on 2026-11-02 after an authorized SSH retry. Both
regressions, all 16 A/B/B/A cases against `86121c724`, and six separate one-sample
profiling/configuration cases passed. Each A/B run has three warmups and 30 measured
samples. The table uses true pooled medians of the 60 raw samples per build and
configuration, not means of run medians:

| Size | Feature Budget | Before (ms) | Resident (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 117.819 | 97.769 | 17.0% |
| 640x480 | 500 | 114.733 | 95.861 | 16.4% |
| 1920x1080 | Unlimited | 246.537 | 215.063 | 12.8% |
| 1920x1080 | 500 | 232.988 | 206.801 | 11.2% |

Every OpenCL quality report field is identical across the four runs for each
configuration, including feature counts, matches, inliers and residual metrics.
Unlimited inliers/RMSE remain 263/0.358588px at VGA and 1300/0.429749px at 1080p;
the 500-feature budget remains a separate quality tradeoff. This single-fixture
experiment shows a gain, not general quality parity or attainment of the
complete-gpu-sift target (roughly 5.92/18.18ms, with different algorithm/workload).

Runner and computed summary: `results/20261102/arc-opencl-resident-pyramid.sh`
and `results/20261102/arc-opencl-resident-pyramid-summary.json` in the SIFT workspace.
Immutable remote stage:
`~/.local/share/sift-extractor-staging/arc-opencl-resident-pyramid-ca1ca46721173a28-retry1`.
Manifest SHA256: `ca1ca46721173a283f88a615c6bef1711d4ed2aabb997b81e70fd658b4d46527`.
Raw reports were retrieved to
`/tmp/sift-arc-resident-results.yKRZW0/resident-pyramid-results`.

### Workgroup Descriptors

Descriptors now assign one 32-lane workgroup to each oriented keypoint. Lanes
partition the support-window columns, accumulate private 128-bin histograms,
and reduce them in fixed lane order using 16.5 KiB of workgroup-local storage.
Normalization, 0.2 clipping and renormalization retain the serial bin order.
There are no floating-point atomics. Results are deterministic on repeated calls,
but the changed accumulation order does not promise bitwise serial equivalence.

The internal `OpenCLDoGExtrema(true)` constructor builds a one-lane serial reference
for differential tests; the existing default constructor selects 32 lanes.
Regression coverage compares 175 descriptors spanning fractional/border positions,
seven orientations and five scales (0.1 through 4096), plus blank reset, empty input
and end-to-end extraction. Maximum local observed bin error is 7.3e-7 against a
2e-5 limit. All ten local tests pass. All four local portable smoke cases
(VGA/1080p, unlimited/500 features) preserve every OpenCL quality report field.

Arc validation completed on 2026-11-02 after an authorized SSH retry. The
175-descriptor regression passed with the same 7.3e-7 maximum bin error. All 16
A/B/B/A cases against `5d2d84fa6` and six separate profiling/configuration cases
passed. Each timing run uses three warmups and 30 measured samples. True pooled
medians of 60 raw samples per build/configuration are:

| Size | Feature Budget | Serial (ms) | Workgroup (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 97.271 | 42.033 | 56.8% |
| 640x480 | 500 | 95.445 | 39.931 | 58.2% |
| 1920x1080 | Unlimited | 213.846 | 164.650 | 23.0% |
| 1920x1080 | 500 | 207.925 | 146.554 | 29.5% |

Every OpenCL quality report field is identical across all four runs for each
configuration. This is measured matching-quality preservation on one resized
fixture, not bitwise descriptor equivalence or general quality parity. CPU/SYCL
control timings also varied between runs; these are observed end-to-end gains,
not isolated kernel speedups. Separate warm original-image profiles put descriptors
at about 10-12ms VGA and 31-39ms 1080p, including host overhead. At 1080p,
extrema/refinement remains about 73-75ms and is now the largest measured stage.
The complete-gpu-sift raw target of roughly 5.92/18.18ms is still unmet.

Runner/summary in the SIFT workspace:
`results/20261102/arc-opencl-workgroup-descriptors.sh` and
`results/20261102/arc-opencl-workgroup-descriptors-summary.json`.
Remote stage: `~/.local/share/sift-extractor-staging/arc-opencl-workgroup-83e7e7ba5ef026fa-retry1`.
Manifest SHA256: `83e7e7ba5ef026fa673ef40dbe912d568ef3fc083dd46a76b0e78e3c8e89e38e`.
Retrieved reports: `/tmp/sift-arc-workgroup-results.mi3yXv/workgroup-descriptor-results`.

### Compacted Refinement

Pyramid detection now uploads each octave once into retained device storage shared
by detection and refinement. Candidate masks remain on-device. Counts for 256-entry
blocks are downloaded for a host prefix sum; GPU scatter preserves the original
scale/row/column candidate order. Only block counts and refined candidate records
are read back, not the full mask. This removes repeated host octave copies,
DoG packing and the second volume upload. It still uploads host DoG levels and
does not yet connect the pyramid's device buffers directly to the detector.

Twelve exact comparisons against the standalone host `detect`/`refine` path cover
dense positive/negative extrema, textured and blank volumes, full/partial blocks,
tiny dimensions and retained-buffer reuse. All ten local tests pass. Arc regression
and all 22 timing/profile cases passed against `3002fcd6a`. No algorithmic quality
approximation was introduced; every OpenCL quality field matches in all four runs.
True pooled medians (60 raw samples/build/configuration):

| Size | Feature Budget | Before (ms) | Compacted (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 41.798 | 38.336 | 8.3% |
| 640x480 | 500 | 40.289 | 36.354 | 9.8% |
| 1920x1080 | Unlimited | 166.652 | 97.144 | 41.7% |
| 1920x1080 | 500 | 149.884 | 76.016 | 49.3% |

Warm 1080p extrema/refinement profiles fell to about 8-10ms. Remaining major costs
are pyramid construction and orientation/descriptor sampling; the raw reference
target remains unmet. Evidence: SIFT workspace `results/20261102/arc-compaction-summary.json`,
runner `results/20261102/arc-opencl-milestone.sh`, local reports
`/tmp/sift-arc-compaction-results.Kwg4kg/milestone-results`, remote stage
`~/.local/share/sift-extractor-staging/arc-compaction-d266f47fcec2f0d8`.
Manifest SHA256: `d266f47fcec2f0d852662e08c6e4453a2c2e0c28f9975439e9480ca7b8f6603b`.

### Deferred Resident Completion and Host Reserves

Resident extraction now submits the Gaussian/DoG pyramid without an immediate
completion wait, then queues detection on the same retained in-order queue.
The detector's completion wait covers both stages. The internal pyramid builder
accepts `wait_for_completion=false` only for device-only results; defaults and
host-pixel outputs remain synchronous. Borrowed device handles must be consumed
on that queue or explicitly synchronized before use elsewhere, and remain valid
only until the next build or owner destruction. Upload data is copied into owned
storage before returning; enqueue failures still drain the queue. Profiling forces
the original pyramid wait so convolution events are complete before querying them.
Profiled stage timings therefore do not measure the deferred-completion gain.
Host feature assembly also reserves its packed points, layout, ordered points,
orientations and final features. All stages, feature counts and arithmetic remain
unchanged. Candidate blocks remain 64 entries with one shared host/kernel constant.

All 10 local tests, two profiled focused tests, both Arc regressions and the
30-case Arc matrix pass. Host-output tests compare every Gaussian/DoG pixel with
both completion flags. Existing exact resident/host feature, capacity-growth,
blank/reconfigured reuse and serial descriptor regressions exercise the deferred
extraction path. All paired matching records are identical. Against `f31094955`,
60 pooled raw samples per build/configuration give:

| Timing Mode | Size | Feature Budget | Before (ms) | After (ms) |
| --- | --- | --- | --- | --- |
| Isolated OpenCL | 640x480 | Unlimited | 5.972 | 5.638 |
| Isolated OpenCL | 1920x1080 | Unlimited | 17.519 | 16.959 |
| Rotated backends | 640x480 | Unlimited | 7.758 | 7.126 |
| Rotated backends | 640x480 | 500 | 7.311 | 6.347 |
| Rotated backends | 1920x1080 | Unlimited | 20.562 | 20.345 |
| Rotated backends | 1920x1080 | 500 | 17.476 | 17.099 |

An independent confirmation used six fresh processes per resolution, alternating
VGA/1080p, with three warmups and 30 samples per process. Pooled 180-sample medians
are VGA **5.6683095ms / 176.419 FPS** and 1080p **16.958033ms / 58.969 FPS**.
Every process median exceeds the respective 168.875/54.995 FPS raw reference
target. Both targets are confirmed for **isolated OpenCL**, not rotated timing,
and not quality-equivalent to the simpler reference. Matching records also equal
the full-run baseline. Broad corpus, reference quality adaptation, backend choice
and production qualification remain open; the release performance gate stays off.

The preceding reserve-only build crossed both targets in its full run
(170.725/59.549 FPS), but independent VGA confirmation was only 168.522 FPS
(1080p 58.358 FPS). That failed VGA confirmation is retained in
`results/20261102/arc-target-confirmation-summary.json`; reserve-only results are
in `arc-host-reserve-summary.json`. Direct rectangular descriptor readback and
32-entry candidate blocks were both slower in subsequent probes and were reverted.
Deferred pyramid completion was revisited because detection and the feature
handoff had changed substantially since its earlier inconclusive experiment.

Evidence: SIFT workspace `results/20261102/arc-deferred-resident-summary.json` and
`results/20261102/arc-deferred-confirmation-summary.json`; reports
`/tmp/sift-arc-deferred-resident-results.TtHAlb` and
`/tmp/sift-arc-deferred-confirmation-results.VAjxF4`; payload
`/tmp/sift-arc-deferred-resident.aXReki`; remote stage
`~/.local/share/sift-extractor-staging/arc-deferred-resident-c125bdf4fd346eab`.
Manifest SHA256: `c125bdf4fd346eabc16d9143d5681a615d3172547abcfe7b3d819515e2249631`.
All five returned executable hashes match the staged binaries; the same manifest
was verified again before the independent confirmation.

### Fused Refinement and Split Descriptor Bins

Resident compaction now refines each candidate directly into its stable prefix
slot, avoiding an intermediate candidate buffer and a separate launch. Detection
blocks contain 64 mask entries; the prefix scan still uses 256 lanes. The same
refinement helper and lossless capacity retry are retained. The host-reference
path still compacts then refines separately. Resident detector profiles report
zero separate compact time; `refine_device_ms` includes fused compaction.

Descriptors use 32 lanes, two per spatial cell, with four ordered orientation
bins per lane. Support bounds, sample order, interpolation and lane-zero ordered
normalization are unchanged. The serial comparison still reports zero maximum
descriptor-bin error on the 687-case test.

All 10 local tests, profiled focused checks, and Arc's expanded regression and
30 matrix cases pass, with identical paired quality records. Against `42b60c766`,
60 pooled samples/build give isolated unlimited VGA 6.386 -> 5.956ms (167.90 FPS)
and 1080p 18.006 -> 17.479ms (57.21 FPS). VGA remains 0.6% below its 168.875 FPS
raw target; 1080p exceeds 54.995 FPS. Short probes crossing VGA were not confirmed
by this longer run. Rotated medians improve for all four configurations:
VGA unlimited 8.040 -> 7.967ms, VGA500 7.254 -> 7.187ms, 1080p unlimited
21.162 -> 20.473ms, 1080p500 18.415 -> 17.460ms. Reference quality parity and
broader-corpus qualification remain outstanding.

Evidence: SIFT workspace `results/20261102/arc-fused-refinement-summary.json`;
reports `/tmp/sift-arc-fused-refinement-results.RM8J37`; payload
`/tmp/sift-arc-fused-refinement.2a1cB3`; remote stage
`~/.local/share/sift-extractor-staging/arc-fused-refinement-b410f3b7012109fd`.
Manifest SHA256: `b410f3b7012109fda2707b8c9f79de2ae83284d1104d898064be768ab7fa902e`.
All five returned executable hashes matched the staged binaries. Feature-only
and all-octave deferred readback probes were reverted after negligible gains.

### Resident Feature Handoff

Orientation peaks now emit counts for a stable device prefix scan. A packing
kernel builds descriptor points/layout directly from the resident orientation
output. Descriptor workgroups guard against the actual count and retained
capacity; insufficient capacity triggers a lossless pack/descriptor retry before
return. Host angle readback remains for public feature records, but no host wait
or point/layout re-upload separates orientation and descriptors. Standalone
feature APIs and serial arithmetic remain references.

The existing multi-orientation fixture now explicitly requires more orientations
than input points, forcing initial capacity growth while checking exact feature
records. All 10 local tests, profiled refinement checks, and Arc's expanded
regression and 30 matrix cases pass. Paired quality records remain identical.
Against `c6b83b8c5`, 60 pooled samples/build give isolated unlimited VGA
6.672 -> 6.337ms (157.80 FPS) and 1080p 18.109 -> 17.889ms (55.90 FPS). The
1080p median exceeds the measured 54.995 FPS raw reference target in this run;
VGA remains below 168.875 FPS. This is not quality parity with that reference,
and the narrow margin and run-to-run variation require caution. Rotated medians:
VGA unlimited 8.526 -> 8.398ms, VGA500 7.402 -> 7.314ms, 1080p unlimited
24.282 -> 23.410ms, 1080p500 17.623 -> 17.995ms (2.1% regression).

Profiles mark `resident_feature_handoff=1`: `orientation_ms` is setup/submission
wall time, while `descriptor_ms` includes the shared GPU completion wait and host
decoding. Neither is an isolated kernel time. Batch event profiles retain separate
orientation/descriptor device times; descriptor events describe the final attempt
on growth frames, while total wall time includes retries. Scratch-byte totals
include retained resident handoff buffers. No profiling events are added normally.

Evidence: SIFT workspace `results/20261102/arc-resident-features-summary.json`;
reports `/tmp/sift-arc-resident-features-results.EsZNXy`; payload
`/tmp/sift-arc-resident-features.a6MJ8B`; remote stage
`~/.local/share/sift-extractor-staging/arc-resident-features-ccbbe5a150f911df`.
Manifest SHA256: `ccbbe5a150f911df371a9da9eea2ed71e9181c407a0eaf263aa274422f3849d7`.
All five returned executable hashes matched the staged binaries.

### Subgroup Orientation Sampling

When `cl_intel_subgroups` is available, lanes prepare successive orientation
samples and broadcast their contributions within each subgroup. Every bin still
accumulates in row-major order; support, exponential weights and smoothing are
unchanged. A 32-lane subgroup is requested only when the device advertises that
size and the required-subgroup-size extension is available. Other subgroup sizes
use the same dynamic loop; devices without the extension retain the previous
bin-owned path. The serial reference remains unchanged.

All 10 local tests, profiled refinement checks, and Arc's expanded regression and
30 matrix cases pass. The 687 orientation inputs still produce 1,351 exactly
equal records, and paired matching-quality records are identical. Against
`a06af7e2d`, 60 pooled samples/build give isolated unlimited VGA 7.042 -> 6.678ms
(149.74 FPS) and 1080p 18.739 -> 18.642ms (53.64 FPS). The 1080p gain is only 0.5%.
Rotated medians are VGA unlimited 8.283 -> 8.702ms (5.1% regression), VGA500
7.703 -> 7.632ms, 1080p unlimited 25.612 -> 24.650ms, and 1080p500
17.955 -> 18.574ms (3.4% regression). Both reference targets remain unmet.
Unsupported-device fallback paths are retained but not hardware-qualified by
these two Intel machines. This is not broad quality or performance parity.

Evidence: SIFT workspace `results/20261102/arc-subgroup-orientation-summary.json`;
reports `/tmp/sift-arc-subgroup-orientation-results.DciDDi`; payload
`/tmp/sift-arc-subgroup-orientation.2VHPo1`; remote stage
`~/.local/share/sift-extractor-staging/arc-subgroup-orientation-8817d210b3459d56`.
Manifest SHA256: `8817d210b3459d56ac09c4a0bd2e039d5147c2a8b0cffd2546b18e6a14e536a2`.
All five returned executable hashes matched the staged binaries. Separate parallel
smoothing and 8x32 Gaussian tile probes were reverted after mixed short-run results.

### Device Candidate Scan

Resident detection now fuses extrema testing and integer block counting, scans
counts on-device in stable mask order, and uses retained candidate capacity.
Compaction and refinement are bounded by that capacity. The actual count is read
with the output; overflow grows capacity and reruns compaction/refinement before
returning any records. No candidates are silently dropped. Normal retained calls
need one detector completion wait, while growth can need a second. Host-reference
detection remains synchronous, and refinement arithmetic is shared unchanged.

`SIFT_OPENCL_PROFILE=1` additionally emits `OPENCL_DETECTION_PROFILE` with fused
extrema/count, scan, compact and refine device-event times. On growth calls,
compact/refine fields describe the final attempts, not the discarded bounded
attempts. Wall timing includes all attempts. Profiling adds no events or waits
when disabled. Device-event and wall times overlap and must not be added.

All 10 local tests, the profiled detector/refinement tests, and Arc's expanded
capacity grow/shrink/blank regression and 30 matrix cases pass. Matching-quality
records are exactly identical for each paired configuration. Against `c0907703b`,
60 pooled samples/build give isolated unlimited VGA 7.453 -> 6.969ms (143.48 FPS)
and 1080p 19.486 -> 19.294ms (51.83 FPS). Rotated medians are VGA unlimited
8.700 -> 8.461ms, VGA500 8.158 -> 7.667ms, 1080p unlimited 25.216 -> 25.943ms
(2.9% regression), and 1080p500 18.917 -> 18.384ms. The gain is primarily VGA;
this is not a uniform speedup. Both raw reference targets remain unmet, and one
fixture does not establish broad quality parity.

Evidence: SIFT workspace `results/20261102/arc-device-scan-summary.json`; reports
`/tmp/sift-arc-device-scan-results.MII3BN`; payload `/tmp/sift-arc-device-scan.eTiKhb`;
remote stage `~/.local/share/sift-extractor-staging/arc-device-scan-f6e82b29d9fbbf99`.
Manifest SHA256: `f6e82b29d9fbbf992436a1f6af8af25cbb34c3e0e75c54b6a00354b2889cde69`.
All five returned executable hashes matched the staged binaries.

### Packed Gradient Launch

Gaussian levels now use aligned views of a retained backing buffer when its
size fits device-allocation and signed-index limits. Oversized layouts retain
individual buffers and per-level gradient launches. Populated gradient planes
are aligned to 256-element workgroups, allowing one launch with workgroup-uniform
level lookup. Borders, hypot/atan2 and feature calculations are unchanged.
Views are invalidated on layout changes and released before their parent.

All 10 local tests and Arc's expanded regression/30 cases pass, with exactly
identical matching-quality records. Paired rotating medians against `620b413ef`
(60 samples/build): VGA unlimited 9.208 -> 9.389ms, VGA500 8.422 -> 8.226ms,
1080p unlimited 26.061 -> 25.699ms, 1080p500 18.562 -> 18.806ms. These are mixed
small changes, not a uniform speedup. Isolated unlimited medians improve from
7.620 -> 7.291ms at VGA (137.16 FPS) and 19.591 -> 19.407ms at 1080p (51.53 FPS).
Targets remain unmet. A separate deferred-pyramid-completion probe gave no clear
1080p gain and was reverted; synchronous completion semantics remain unchanged.

Evidence: SIFT workspace `results/20261102/arc-packed-gradients-summary.json`
and `results/20261102/arc-packed-gradients-isolated-summary.json`; reports
`/tmp/sift-arc-packed-gradients-results.5Pycte`; remote stage
`~/.local/share/sift-extractor-staging/arc-packed-gradients-42a2b62249e06e3f`.
Manifest SHA256: `42a2b62249e06e3fbe85a1fc3c3737cde4ad9d4a20f1e7dc0e546a5b137836e3`.
All five returned executable hashes matched the staged binaries.

### Centralized Input Validation

Detection/extraction now rely on the combined pyramid's finite-pixel validation,
which runs before pyramid allocation/submission. Its boolean reduction replaces
an early-exit scalar loop; redundant entry-point scans are removed. Non-finite
inputs still throw `std::invalid_argument`, now with the pyramid's diagnostic.
NaN and positive/negative infinity are checked at the start, middle and end of
the input through both entry points, followed by valid-frame reuse.

All 10 local tests and Arc's expanded regression/30 comparison cases pass.
All matching-quality records remain identical. Paired pooled rotating medians
against `ba025dde0` (60 samples/build):

| Size | Feature Budget | Before (ms) | After (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 9.053 | 9.395 | -3.8% |
| 640x480 | 500 | 8.565 | 8.455 | 1.3% |
| 1920x1080 | Unlimited | 27.102 | 25.817 | 4.7% |
| 1920x1080 | 500 | 20.223 | 18.651 | 7.8% |

Isolated unlimited medians improve from 7.810 to 7.600ms at VGA (131.58 FPS),
and 21.743 to 19.709ms at 1080p (50.74 FPS), also 60 samples/build. Rotating VGA
unlimited regressed in this run; no uniform improvement across modes is claimed.
Throughput targets remain unmet. Evidence: SIFT workspace
`results/20261102/arc-finite-scan-summary.json` and
`results/20261102/arc-finite-scan-isolated-summary.json`; reports
`/tmp/sift-arc-finite-scan-results.K0Mrdk`; remote stage
`~/.local/share/sift-extractor-staging/arc-finite-scan-46eed312f59387ef`.
Manifest SHA256: `46eed312f59387ef334be51d1f3f1ff3e44ca2a3328a1d579ca146bcea1989a1`.
All five returned executable hashes matched the staged binaries.

### Isolated Timing Diagnostic

`validate_sift_pair IMAGE REPORT ITERATIONS CONFIG opencl-only` computes all
three backend quality reports but times repeated OpenCL extraction without
interleaved CPU/SYCL extractions. The default rotating comparison is unchanged.
Reports identify `timing_mode=opencl_only`, set `rotating_backend_order=0`, and
omit unmeasured CPU/SYCL latencies and ratios. Input conversion, transfers and
host feature results remain timed; initial construction remains excluded.

A same-binary rotating/isolated/isolated/rotating Arc diagnostic (60 samples/mode)
measured VGA 9.179ms rotating versus 7.940ms isolated (125.95 FPS), and 1080p
26.240ms versus 21.325ms (46.89 FPS). Quality records are exactly identical.
This is a measurement-workload effect, not another implementation speedup or a
verified clock/power explanation. Neither isolated result reaches the measured
reference targets of 168.875 and 54.995 FPS. Reference workload/quality differences
also remain unresolved; these results do not establish quality parity.

Evidence: SIFT workspace `results/20261102/arc-timing-isolation-summary.json`;
reports `/tmp/sift-arc-timing-isolation-results.8Ry98S`; remote stage
`~/.local/share/sift-extractor-staging/timing-isolation.AoCkFz`.
Verified executable SHA256:
`38a124ea488d59c9dccac6423b7c2ff5d02319a946079a949014d88fa4f3bf7d`.

Subsequent grouped-orientation probes (four lanes/nine bins and 12 active
lanes/three bins) were slower on Arc and reverted. Explicit padded 32x8 extrema
workgroups showed no clear gain and were also reverted.

### Fused Gaussian Passes

For radii up to 12, the combined pyramid uses a 16x16 tile with horizontal
halo rows in local memory, followed by vertical convolution and optional DoG
output. Tap order and clamped borders match the standalone two-pass reference
exactly in tests. Larger radii retain that reference path. Default convolution
launches fall from 42 to 21; profiling reports fused device time separately.

All 10 local tests, Arc pyramid/refinement regressions and 22 comparison cases
pass. Matching-quality records remain identical. Paired pooled medians against
`36d80bc80` (60 samples/build):

| Size | Feature Budget | Before (ms) | Fused (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 9.486 | 9.336 | 1.6% |
| 640x480 | 500 | 9.289 | 8.455 | 9.0% |
| 1920x1080 | Unlimited | 27.790 | 26.765 | 3.7% |
| 1920x1080 | 500 | 22.665 | 19.070 | 15.9% |

Targets remain unmet. Evidence: SIFT workspace
`results/20261102/arc-fused-passes-summary.json`; reports
`/tmp/sift-arc-fused-passes-results.0NZz7Z/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-fused-passes-4dc3835b83b1d26b`.
Manifest SHA256: `4dc3835b83b1d26bc61c3ae89d6a4aca9815d1847d4765eaff75edc077b743eb`.
All five returned executable hashes matched the staged binaries.

### Spatial-Bin Descriptors

Descriptors now use 16 lanes, each owning the eight orientation bins of one
spatial cell. Geometry and sample reads are shared across those bins; each bin
still accumulates samples in row-major order. Support, interpolation, clipping
and normalization are unchanged. The serial reference remains available.
All 10 local tests and Arc's regression/22 comparison cases pass; 687 descriptor
cases meet the existing 2e-5 bound (printed maximum error 0.00000000), and all
matching-quality records remain identical.

Paired pooled medians against `83f8276c1` (60 samples/build):

| Size | Feature Budget | Before (ms) | Spatial (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 9.714 | 9.705 | 0.1% |
| 640x480 | 500 | 9.562 | 9.432 | 1.4% |
| 1920x1080 | Unlimited | 29.891 | 27.788 | 7.0% |
| 1920x1080 | 500 | 23.588 | 22.315 | 5.4% |

No meaningful VGA unlimited gain is established; throughput targets remain unmet.
Evidence: SIFT workspace `results/20261102/arc-spatial-bins-summary.json`; reports
`/tmp/sift-arc-spatial-bins-results.XbTTkn/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-spatial-bins-a6e243ad789a0413`.
Manifest SHA256: `a6e243ad789a0413c24c126d68c32aa3fb072af5072a22f08ff3233ddbdea7a2`.
All five returned executable hashes matched the staged binaries.

### Shared DoG Volumes

Aligned DoG levels are sub-buffer views of one retained volume per octave.
Detection verifies their parent and offsets before consuming that volume directly,
avoiding packing copies. Unaligned planes retain the individual-buffer path.
Configuration changes invalidate the views before rebuilding them; views are
released before their owning volumes. This retains synchronous borrowed-buffer
semantics, not a new concurrency or device-recovery guarantee.

All 10 local tests and Arc's expanded aligned/unaligned reuse regression pass.
All matching-quality records remain identical. Paired pooled medians against
`5cdacee9f` (60 samples/build):

| Size | Feature Budget | Before (ms) | Shared (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 10.564 | 9.761 | 7.6% |
| 640x480 | 500 | 10.267 | 9.680 | 5.7% |
| 1920x1080 | Unlimited | 30.639 | 29.772 | 2.8% |
| 1920x1080 | 500 | 24.798 | 21.500 | 13.3% |

Targets remain unmet. Evidence: SIFT workspace
`results/20261102/arc-shared-dog-summary.json`; reports
`/tmp/sift-arc-shared-dog-results.4bPG3l/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-shared-dog-fbb49a49fe288bd4`.
Manifest SHA256: `fbb49a49fe288bd4b0dc75b47e208a8d7265ed37cc2b0cd547a653664c9ce9be`.
All five returned executable hashes matched the staged binaries.

### Mapped Pyramid Input

Pyramid input now uses a dedicated retained `CL_MEM_ALLOC_HOST_PTR` buffer,
mapped with write invalidation, filled on the host and unmapped before GPU use.
Standalone primitives remain unchanged. Exact pyramid and feature regressions,
all 10 local tests and Arc's 22 timing/profile cases pass; all matching-quality
records are identical. Paired pooled medians (60 samples/build), against `fe1e9b7f1`:

| Size | Feature Budget | Before (ms) | Mapped (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 10.632 | 10.510 | 1.2% |
| 640x480 | 500 | 10.693 | 10.188 | 4.7% |
| 1920x1080 | Unlimited | 32.909 | 30.717 | 6.7% |
| 1920x1080 | 500 | 25.705 | 25.106 | 2.3% |

Optional `OPENCL_PYRAMID_PROFILE` now reports convolution device-event totals and
upload/submission/completion wall times. They overlap and must not be added as
independent costs. Warm 1080p upload probes fell from roughly 1-2.3ms to 0.6-1ms.
Fixed-radius Gaussian specialization showed no clear gain and was reverted.
Arc's advertised extensions do not include `cl_khr_command_buffer`; no system or
driver changes were made. Throughput targets remain unmet.

Evidence: SIFT workspace `results/20261102/arc-mapped-input-summary.json`; reports
`/tmp/sift-arc-mapped-input-results.hnp7qT/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-mapped-input-24708e44bd776bf0`.
Manifest SHA256: `24708e44bd776bf05756c1f9c69de57e967a88d4e4c15e85089bfe93d99b94c9`.
All five returned executable hashes matched the staged binaries.

### Batched Detection Phases

Resident detection now retains scratch for each octave and performs two phases:
enqueue all extrema/count operations and wait once, then enqueue all compaction/
refinement operations and wait once. Counts, offsets and refined records use
nonblocking transfers with protected host lifetimes. Stable block prefix sums and
octave ordering are unchanged. The synchronous host detector remains the reference.
Per-octave scratch increases retained detector memory relative to the former single
reused octave allocation; capacity is released at extractor destruction.

All 10 local tests and Arc regression plus 22 timing/profile cases passed. Added
exact host-reference comparisons across octave counts 8, 4, 2, 1, 4 cover growing,
shrinking and too-small octaves. Full feature equivalence and all quality fields
remain unchanged. True pooled medians (60 samples/build), against `cbf55bb9e`:

| Size | Feature Budget | Before (ms) | Batched (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 11.360 | 10.524 | 7.4% |
| 640x480 | 500 | 11.480 | 10.572 | 7.9% |
| 1920x1080 | Unlimited | 33.094 | 31.953 | 3.4% |
| 1920x1080 | 500 | 26.682 | 25.630 | 3.9% |

The paired comparison improved, but absolute 1080p timings are higher than the
previous milestone's run. Do not treat cross-run timings as a controlled speedup.
Reference throughput targets remain unmet. Evidence: SIFT workspace
`results/20261102/arc-batched-detection-summary.json`; reports
`/tmp/sift-arc-batched-detection-results.9VWurW/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-batched-detection-22d7032ee9255596`.
Manifest SHA256: `22d7032ee92555961682626d1ede6be1f243d3efbda4fcb0364ea97dcdd1d33c`.
All five returned manifest executable hashes matched the staged binaries.

### Merged Feature Launches

Populated levels' gradients now occupy a checked, packed device volume. Per-point
metadata supplies image dimensions and gradient offsets, allowing one orientation
launch and one descriptor launch per image, with one upload/readback per phase.
Gradient preparation still launches per level. Stable level/keypoint/orientation
ordering, serial references, response caps and synchronous return are unchanged.
Offset accumulation rejects volumes exceeding signed kernel indexing. Metadata
and result buffers remain alive through phase completion and error-path drains.

All 10 local tests and Arc regression plus 22 timing/profile cases passed. Exact
host-pipeline/reconfiguration comparisons, 1,351 exact oriented records and 687
descriptor comparisons pass. All matching-quality fields were identical across
A/B/B/A. True pooled medians (60 samples/build), against `2a9d9258f`:

| Size | Feature Budget | Before (ms) | Merged (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 21.034 | 11.783 | 44.0% |
| 640x480 | 500 | 18.691 | 11.363 | 39.2% |
| 1920x1080 | Unlimited | 40.090 | 29.593 | 26.2% |
| 1920x1080 | 500 | 32.193 | 26.958 | 16.3% |

Unlimited throughput is approximately 84.9/33.8 FPS at VGA/1080p. The reference
targets remain unmet. Scratch in the 1080p probe was 67,840,740 bytes, approximately
64.7 MiB, retained at high-water capacity. Profile `groups=1` now means one merged
feature launch, while coarse `feature_groups` still counts populated pyramid levels.
Single-fixture quality stability does not establish broader quality parity.

Evidence: SIFT workspace `results/20261102/arc-gradient-atlas-summary.json`; reports
`/tmp/sift-arc-gradient-atlas-results.SCIif4/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-gradient-atlas-e8b606c7a1c6b441`.
Manifest SHA256: `e8b606c7a1c6b441e3c6119b2711a42cf54598ca24c4e8c499b2b740298b2375`.
All five returned manifest executable hashes matched the staged binaries.

### Fused Gaussian and DoG Output

Combined pyramid construction now writes each DoG plane from the vertical Gaussian
pass, eliminating a separate subtraction launch and upper-image reread. Standalone
blur and subtraction remain unchanged reference paths. Exact level comparisons
include odd 257x129 images, sigma 16 with one interval, and 32 intervals on tiny
images, plus blank/reconfigured reuse. An earlier tiled-loading experiment showed
no useful Arc gain and was reverted.

The parallel descriptor kernel also hoists support scaling into one standard
reciprocal per keypoint. This is not a native/fast-math substitution; nevertheless,
reciprocal multiplication can differ from division in floating-point rounding.
The unchanged serial division reference remains covered by the 2e-5 bin-error
gate. Arc's 687-case test printed zero maximum error to eight decimal places.
All 1,351 oriented records still matched exactly.

All 10 local tests, expanded Arc pyramid/refinement regressions, and 22 timing/
profile cases passed. All matching-quality fields were identical across A/B/B/A.
True pooled medians (60 samples/build), against `5a5e42b6c`:

| Size | Feature Budget | Before (ms) | Fused (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 22.045 | 20.817 | 5.6% |
| 640x480 | 500 | 20.306 | 18.714 | 7.8% |
| 1920x1080 | Unlimited | 43.458 | 40.862 | 6.0% |
| 1920x1080 | 500 | 34.725 | 32.230 | 7.2% |

Unlimited throughput is approximately 48.0 FPS at VGA and 24.5 FPS at 1080p,
still below the measured reference's 168.875 and 54.995 FPS. No algorithmic stages
were removed. Single-fixture matching stability is not a general quality guarantee,
and the simpler reference still lacks common-validator quality measurements.

Evidence: SIFT workspace `results/20261102/arc-fused-pyramid-summary.json`; reports
`/tmp/sift-arc-fused-pyramid-results.nySDwX/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-fused-pyramid-ba2aaf7beefadecb`.
Manifest SHA256: `ba2aaf7beefadecb1b858a8c2806b00589e7d8af70666d5ccfbfd58ca3a4576e`.
All five returned manifest executable hashes matched the staged binaries.

### Batched Feature Stages

Extraction now queues all populated levels' orientations, waits once, then queues
all descriptors and waits once. Per-level retained scratch preserves gradients
across phases. Host point uploads and output reads are nonblocking inside each
phase; buffers remain alive through completion, including an error-path queue
drain. Standalone feature APIs remain synchronous. Output order and response caps
are unchanged. Orientation uses one lane per bin in a 64-lane group, retaining
the original accumulation, smoothing and peak-selection order.

All 10 local tests and Arc regression plus 22 timing/profile cases passed.
687 orientation inputs produced 1,351 exactly equal oriented records versus the
serial path; descriptor comparisons and full host-path equivalence also passed.
All matching-quality fields were identical across A/B/B/A. True pooled medians
(60 samples/build), against `680434e62`:

| Size | Feature Budget | Before (ms) | Batched (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 26.403 | 21.715 | 17.8% |
| 640x480 | 500 | 27.201 | 20.089 | 26.1% |
| 1920x1080 | Unlimited | 48.890 | 43.683 | 10.7% |
| 1920x1080 | 500 | 43.393 | 34.749 | 19.9% |

CPU control medians rose materially in the candidate runs (1080p approximately
247-248ms to 293-294ms). These are observed end-to-end results, not isolated kernel
speedups. Warm profile calls ranged approximately 37-47ms at 1080p. The reference
throughput target remains unmet at both sizes.

Memory tradeoff: feature scratch retained 67,806,192 bytes (64.7 MiB) for the
1080p fixture, in addition to the pyramid and detector buffers. Scratch keeps its
high-water capacity until extractor destruction. `OPENCL_BATCH_FEATURE_PROFILE`
reports aggregate device-event time and scratch capacity after each phase completes.
Standalone calls retain `OPENCL_FEATURE_PROFILE` reporting. These profiles are
separate from acceptance timing runs; phase wall times include transfers and host work.

Evidence: SIFT workspace `results/20261102/arc-batched-features-summary.json`;
reports `/tmp/sift-arc-batched-features-results.Dzhul3/milestone-results`;
remote `~/.local/share/sift-extractor-staging/arc-batched-features-7381155db578d71b`.
Manifest SHA256: `7381155db578d71b7fe54108a88723a784255e36c1f320dda092c8fb86ad9d17`.
All five returned manifest executable hashes matched the staged binaries.

### Bin-Owned Descriptors

The parallel descriptor kernel now assigns one lane to each of 128 bins. Each lane
visits the bounding box of its rotated spatial bin with a conservative one-pixel
guard, then applies the original support and interpolation predicates. Contributions
remain in row-major order; no samples, octaves, orientations or descriptor bins are
dropped. Normalization is still serial in bin order. Local storage falls from
16.5 KiB to 512 bytes. The serial reference retains its original general `fmod`;
the parallel path wraps the bounded angle range with exact subtractions.

All 10 local tests and Arc regression plus 22 timing/profile cases passed. The
687 deterministic descriptor cases cover fractional coordinates, angles, borders,
small/large scales, repeatability and blank images. Observed Arc maximum bin error
against the serial reference was zero. All matching-quality report fields remained
identical across A/B/B/A. True pooled medians (60 samples/build), against `9f42d43a6`:

| Size | Feature Budget | Before (ms) | Bin-Owned (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 28.247 | 26.788 | 5.2% |
| 640x480 | 500 | 27.768 | 26.766 | 3.6% |
| 1920x1080 | Unlimited | 62.106 | 48.659 | 21.7% |
| 1920x1080 | 500 | 45.446 | 43.778 | 3.7% |

The throughput target remains unmet. Single-fixture quality stability does not
establish general quality parity. Direct local-memory accumulation showed only
1-3% changes and was reverted; native exponential did not show a meaningful gain
and was also reverted. No approximate native math is retained.

Set `SIFT_OPENCL_PROFILE=1` before constructing the extractor to additionally enable
OpenCL event timing. `OPENCL_FEATURE_PROFILE` separates device kernel time from
host preparation and enqueue/readback wall time. Coarse stage timings remain wall
clock; profiling runs are separate from acceptance timing runs.

Evidence: SIFT workspace `results/20261102/arc-bin-owned-summary.json`; local reports
`/tmp/sift-arc-bin-owned-results.ubuyPE/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-bin-owned-f9b7d63529044540`.
Manifest SHA256: `f9b7d63529044540d8458d5517303f3a9ed149236f81954a764433b5d40dc4b3`.
All five returned run manifests match the staged executable hashes.

### Resident Pyramid Consumption

Image extraction now keeps both Gaussian and DoG images on-device. DoG levels are
copied device-to-device into the retained contiguous detection/refinement volume;
gradient kernels read Gaussian buffers directly. There are no Gaussian/DoG host
allocations or image readbacks in this path, and no feature-image re-upload or
host pixel scan. Block-prefix counts, keypoints, orientations and descriptors still
cross the host boundary, so this is not an entirely device-only extractor.

The internal pyramid's `keep_on_device` option returns borrowed buffer handles
valid only until its next build or destruction. The extractor consumes them
synchronously on the shared in-order queue. Gradient cache state is reset at each
extraction; standalone host-vector APIs retain pixel validation and mutation
detection. The default pyramid API still returns independent host vectors.
Exact full-feature equivalence against an assembled host pipeline and all ten
local tests pass. Arc regression and all 22 timing/profile cases passed against
compaction milestone `e40d198ba`. All OpenCL quality report fields are identical
across four A/B/B/A runs per configuration. True pooled medians (60 samples/build):

| Size | Feature Budget | Before (ms) | Resident (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| 640x480 | Unlimited | 38.207 | 28.470 | 25.5% |
| 640x480 | 500 | 36.473 | 27.580 | 24.4% |
| 1920x1080 | Unlimited | 96.990 | 61.400 | 36.7% |
| 1920x1080 | 500 | 80.536 | 44.571 | 44.7% |

CPU control times also shifted materially, so these are observed application-level
gains rather than isolated GPU kernel speedups. Warm 1080p profiles show roughly
11-14ms pyramid, 7-9ms extrema/refinement, 14-15ms orientation and 24-29ms descriptors.
The reference throughput target remains unmet. Evidence: SIFT workspace
`results/20261102/arc-resident-consumption-summary.json`; local reports
`/tmp/sift-arc-resident-consumption-results.wE8Are/milestone-results`; remote stage
`~/.local/share/sift-extractor-staging/arc-resident-consumption-017c74728b0106b3`.
Manifest SHA256: `017c74728b0106b36fb43c0a8704b190da53cc7689530c00c730bef49d34a550`.

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