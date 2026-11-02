<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Broader Quality Diagnostic

## Status

The product quality requirement is **at least as good as CudaSift**, not 95% of
its correspondence count. This requirement is not yet demonstrated. OpenCV remains
a diagnostic reference. complete-gpu-sift is excluded from further acceptance work
and will not be repaired; its results below are historical evidence only.

## Further OpenCL Parity Probes

Checkpoint 50 evaluates representatives of all four remaining optimization areas,
but does not complete or exhaust them. All five candidates below were rejected
and reverted. Extraction arithmetic, defaults, feature selection and matching are
restored to checkpoint 49. The only retained runtime change is opt-in packed-gradient
event timing under `SIFT_OPENCL_PROFILE=1`, reported as
`OPENCL_BATCH_FEATURE_PROFILE kernel=sift_packed_gradients`. Fresh Arc profiling
measures roughly 0.16 ms VGA / 1.22 ms 1080p for this kernel; profiling changes
synchronization and is not used for acceptance timing.

| Probe | VGA Latency Change | 1080p Latency Change | Decision |
| --- | --- | --- | --- |
| Defer host-only scalar counts until the end of each batch | -1.35% | +0.69% | Reject inconclusive tradeoff. |
| Conservative gradient-tile mask, default | +1.42% | -0.29% | Reject general dispatch; cap-500 1080p alone improves 4.59%. |
| Fully subgroup-parallel normalization, clipping and output | +12.58% | +15.29% | Reject. |
| Exact consecutive two-level Gaussian fusion | +3.70% | +12.53% | Reject. |
| Exact GPU first-owner location deduplication | +4.27% | -0.71% | Reject standalone dispatch. |

Positive means slower. Except for the mask, these are screening A/B/B/A runs with
two fresh processes/build/size, three warmups and 30 samples/process (60 pooled).
The mask uses six counterbalanced pairs/build across default, cap-500, contrast-0.1
and sigma-1 at both sizes (180 samples/build/case). No screen is a release gate.
All reported OpenCL quality fields are identical between each candidate and its
baseline at each tested setting. All 12 full mask feature-export comparisons are
byte-identical. Full parallel normalization deliberately changes summation order:
its Arc serial-reference maximum bin difference is 0.00000009, within the existing
0.00002 tolerance; no full-export byte-equality claim is made for that probe.

The cross-scale probe preserves both intermediate Gaussian images, both DoG outputs,
the sequential convolution order, clamped borders and original coefficients.
It fuses levels with first radius <=12 and second radius <=6 using local intermediates;
other levels retain the existing fallback. Every Gaussian/DoG pixel matches the
separate-pass reference in local and Arc pyramid tests. Its slower result does not
rule out other multi-scale designs or establish why it lost; added halo computation,
local memory, indexing and occupancy remain possible costs, not isolated causes.

GPU deduplication uses atomic minimum candidate-index ownership and a second stable
filter pass. Exact host/reference ordering, real localization collisions, candidate
growth/retry and reuse tests pass locally and on Arc. It retains the full refined
record readback, CPU sigma mapping, stable capping and grouping: it is not the fully
device-resident detection-to-description path. Further work must address that
combined boundary rather than treating standalone GPU membership as completion.

The final restored executable is then measured against retained-context SYCL with
six fresh counterbalanced processes/backend/size, three warmups and 30 samples
(180/backend/size). Profiling is off. Same historical 1280x960 input resized to
640x480 and 1920x1080; the latter is upscaled/aspect-changed, not native camera data.
Both isolated timing scopes include conversion/upload/extraction/owned host output,
adapter and logging, excluding initial context/workspace setup, decode/resize and
matching. Native algorithm settings remain different.

| Size | OpenCL ms / FPS | SYCL ms / FPS | OpenCL Excess Latency |
| --- | --- | --- | --- |
| 640x480 | 5.882044 / 170.01 | 3.797873 / 263.31 | 54.88% |
| 1920x1080 | 17.809774 / 56.15 | 15.589012 / 64.15 | 14.25% |

Pooled p95 OpenCL/SYCL is 6.203/3.988 ms VGA and 18.301/15.909 ms 1080p. A
10,000-draw fixed-seed bootstrap of six paired process-median excesses gives 95%
intervals 52.92-58.39% VGA and 13.23-16.62% 1080p. These are exploratory within-host
intervals, not release/held-out qualification. OpenCL has not matched SYCL, nor do
these failed probes establish an inherent API limit. No backend is selected.

OpenCL quality remains 401/1893 inliers, precision 94.799%/91.983%, own-inlier RMSE
0.343096/0.439483 px, exact across final processes. SYCL varies again: 636-641 /
2095-2106 inliers; feature counts remain 1366/1188 and 4939/4071. CudaSift-level
quality and SYCL repeatability remain unresolved. Final local 11/11 and Arc exact
pyramid/refinement suites pass. No held-out acquisition, CUDA rerun, Python or system
changes. The earlier compact-handoff optimization remains retained.

Evidence: workspace `results/20261102/opencl-parity-probes/`, with all successful
probe patches/binaries, tests, raw reports, mask exports, reproducible comparison/
analysis, archive and checksum receipts. Final stage `parity-final-acb1ea0055dd8264`,
manifest `acb1ea0055dd826486dcfaa6d5feb86c68d9eee7fe205699e3f7cb6363dd5387`.
Final executable SHA256
`da541b010112c8d4b96d64e7e9b87caf964e54f0a240f20a9fba215b8f88d9c1`.

## Compact Orientation Handoff

Checkpoint 49 changes host handoff and membership lookup, not SIFT arithmetic,
settings or matching. Resident extraction no longer copies the dense 36-bin angle
grid to the CPU. The existing stable GPU orientation packer writes compact source
indices and angles beside the descriptor inputs; the CPU consumes these records
in the same order. Lossless descriptor-capacity growth/retry remains unchanged.
Exact localized-point deduplication uses a reserved hash set for membership only,
never for output iteration, preserving first occurrence and float equality.
Decoded host refinement records also reserve their known upper bound.

An independent ordered-set test reconstructs raw detect/refine output across four
interval/sigma configurations, exercising 25 actual localization collisions on Arc.
Existing exact host/resident features, secondary orientations, capacity growth,
shrink/blank reuse and reconfiguration tests pass. All 11 local CTest cases pass.
Twelve complete independent-image exports are byte-identical to the baseline:
three shared images (1280x960 speed input and native 800x640 graf views), each with
default, cap-500, contrast-0.1 and sigma-1 settings. This includes positions,
descriptors and export metadata, not just aggregate scores. Every reported OpenCL
quality field is also identical across all 120 measured processes.

Unprofiled Arc runs use alternating before/after and after/before fresh-process
pairs, three warmups and 30 samples/process. Default cases have 12 pairs and 360
samples/build; controls have six pairs and 180 samples/build. Inputs, resizing,
timing scope and development-only quality rules match the previous speed fixture.
The immutable baseline is checkpoint 48 (its validator is identical to 47).

| Configuration | Size | Before (ms) | After (ms) | Latency Reduction |
| --- | --- | --- | --- | --- |
| Default | 640x480 | 5.942807 | 5.863901 | 1.33% |
| Default | 1920x1080 | 18.440068 | 17.677267 | 4.14% |
| Cap 500 | 640x480 | 5.980800 | 5.877607 | 1.73% |
| Cap 500 | 1920x1080 | 15.448220 | 14.976697 | 3.05% |
| Contrast 0.1 | 640x480 | 6.118731 | 5.971379 | 2.41% |
| Contrast 0.1 | 1920x1080 | 20.076443 | 19.402758 | 3.36% |
| Sigma 1 | 640x480 | 5.851041 | 5.652655 | 3.39% |
| Sigma 1 | 1920x1080 | 21.767458 | 19.849405 | 8.81% |

These are pooled median latencies, not release-qualified performance. Default
throughput becomes 170.53/56.57 FPS. A 10,000-draw paired fresh-process bootstrap
of median paired latency reductions gives 95% intervals of 0.92-1.78% for default
VGA, 3.84-4.32% for default 1080p, and 8.51-9.10% for sigma-1 1080p. These are
within-host exploratory intervals, not a held-out or multi-host release gate.
The default gain remains below the 5% meaningful backend-selection threshold.

The initial six default VGA pairs had p95 6.225 -> 6.555 ms (+5.29%), triggering
six additional default pairs. Preserve both results: combined p95 is 6.442 ->
6.507 ms (+1.00%); follow-up-only p95 is 6.574 -> 6.334 ms. The initial tail increase
did not persist, but this sequential investigation is not an independent release
qualification. All measured case medians improve; no measured final p95 regresses
more than 5%. SYCL performance was not remeasured or modified in this checkpoint.

`SIFT_OPENCL_PROFILE=1` additionally emits `OPENCL_HOST_DETECTION_PROFILE` with
`parse_dedup_map_ms` and localized keypoint count, only for resident detection.
This times host decoding/deduplication/mapping after GPU completion, not the
detection kernels. Profiling forces other waits and is kept out of acceptance
timings; short screening profiles are not isolated causal speed measurements.

Evidence: workspace `results/20261102/compact-orientation-handoff/`, including
both preliminary screens, exact binaries/patches, full exports, initial and
follow-up timing reports, reproducible analysis, raw archive and checksum receipts.
Arc stage `compact-final-431c8b0f83a0429f`, payload manifest
`431c8b0f83a0429fb327441195cf2c5e81904ac2e21d58c7a3614419dcf7697e`.
Quality remains below the required demonstrated CudaSift floor; no reference
changed, CUDA rerun, held-out acquisition, backend selection or Python work occurred.

## Profiled Optimization Probes

Checkpoint 48 retains tests and diagnostic evidence only. Both performance probes
below were rejected and fully removed; production extraction source is unchanged
from checkpoint 47 (and the algorithm remains checkpoint 45). No settings, feature
limits, matching rules or quality acceptance thresholds changed.

Fresh Arc profiling of the current speed fixture at 1080p attributes roughly
6.9-7.0 ms to the Gaussian/DoG phase, 3.8-3.9 ms to detection/refinement, and
6.0-6.2 ms to the descriptor/host-output phase. Device descriptor kernel time is
about 2.58 ms, orientation 1.23 ms and detection kernels about 1.61 ms total.
Host-phase times are queue-boundary accounting, not isolated kernel times or
an additive hardware bottleneck breakdown. Profiling forces Gaussian completion
and changes synchronization; these samples are diagnostic, not acceptance FPS.

Two small candidates were tested independently against the exact checkpoint-47
binary on Arc. Unprofiled A/B/B/A uses two fresh processes per build and resolution,
three warmups and 30 measured extractions per process (60 pooled samples/build).
The existing 1280x960 input and resized VGA/1080p configurations are unchanged.

| Probe | VGA Before -> After (ms) | 1080p Before -> After (ms) | Decision |
| --- | --- | --- | --- |
| Cooperative input tile in fused Gaussian | 5.943037 -> 6.267255 | 18.207181 -> 20.274420 | Reject: latency +5.46% / +11.35%. |
| Parallel descriptor clipping and stores, original norm summation order | 5.912551 -> 5.955020 | 18.219835 -> 18.377184 | Reject: no useful gain; pooled latency +0.72% / +0.86%. |

All reported OpenCL quality fields are identical between each candidate and its
baseline at each resolution. This checks aggregate diagnostics, not byte equality
of every feature export. The Gaussian exact-pyramid and extraction tests pass
locally and on Arc for their respective probes. The restored implementation passes
the expanded tests. Neither experiment establishes a new speedup or quality result;
the previous current-extractor benchmark remains applicable.

The retained pyramid tests add the radius-12 fused boundary, the adjacent radius-13
fallback and a one-pixel image with a full halo. Every Gaussian/DoG level is compared
exactly to the separate-pass implementation, for textured and blank inputs and both
host completion flags. Existing odd-size, buffer-reuse and large-radius cases remain.

Final local full build and all 11 CTest cases pass. The restored-code pyramid,
refinement and all-backend scorer/export suites pass on Arc. The final production
validator is byte-identical to the checkpoint-47 baseline executable; no new FPS
claim is made. Final retained-test stage `probes-final-43931c8221da24d9`, manifest
`43931c8221da24d9ab5ce4a1fb712abedad330f3a4d19e46540f087c91d8a640`.

Input tiling can add local-memory traffic, indexing, barriers and occupancy costs;
these runs do not isolate which cost caused its regression. Similarly, parallelizing
small descriptor operations did not justify its added synchronization. Do not retry
these exact candidates as assumed improvements. Next structural work should target
cross-scale reuse or the host-visible detection/grouping boundary with new profiles
and exact ordering, lossless capacity handling and quality checks. Detection already
reads back only its total count plus refined records; there is no redundant full
count-array readback in the resident path to simply delete.

Workspace evidence: `results/20261102/opencl-profiled-probes/` contains fresh profile
logs, both rejected patches, raw timing/quality reports and summaries. Gaussian Arc
stage `tiled-gaussian-dd79c077272fd997`, manifest
`dd79c077272fd997cba89abc2da26c4edf013e4790b138c1744064276e501cc9`;
descriptor stage `descriptor-stores-0c6857aa1fd74ff2`, manifest
`0c6857aa1fd74ff21de66dbcdd4ed69cb2dc05c882946e69d3c1ca9097a46327`.
Raw evidence archive and `opencl-profiled-probes-receipts.sha256` are alongside it.
No CudaSift rerun, held-out acquisition, backend selection or Python work occurred.

## Independent-image Exports and Viewpoint Smoke

Checkpoint 47 adds independent-image exports using the existing extraction adapters;
it changes no extraction kernel, default or matching threshold:

```bash
validate_sift_pair --export-features first.pgm first-features.json config.json opencl
validate_sift_pair --export-features second.pgm second-features.json config.json opencl
validate_sift_pair --score-external first-features.json second-features.json \
  geometry.json scored.json
```

Use `opencv` or, when compiled, `sycl` in place of `opencl`. `config.json` can be
`{}` for unchanged defaults. The exporter never resizes; configuration `width` and
`height` are rejected. Preprocess both images explicitly, preserve their hashes,
and express known geometry in the exported pixel coordinates. Both images must
have the same dimensions for the existing external scorer. This is separate from
`quality-export`, which still generates an affine-transformed second image.

Files contain float32 Nx2 `positions` and Nx128 `descriptors`, including valid
zero-row matrices for empty images. Exported positions must be finite and in-image;
descriptors must be finite and nonzero. Images must decode successfully and be at
most 3840x2160. Exports above 32768 records fail rather than being truncated by
the exporter. Metadata `capacity:32768` is this export/scorer ceiling, not an
intrinsic OpenCV feature cap. The existing SYCL extractor separately has a fixed
32768-feature allocation. `feature_limit` records the requested `nfeatures` (zero
means no requested limit); backend cap/selection semantics are not equivalent.

Metadata intentionally sets `parameters_equivalent:0`. Algorithm-control fields
record configuration values, not a claim that every backend implements them:

| Backend | Effective controls | Controls not shared |
| --- | --- | --- |
| OpenCL | `octaves`, `intervals`, `sigma`, `opencl_contrast`, `edge_threshold`, feature limit | Edge rejection uses `(edge+1)^2/edge`; default 12.1. |
| SYCL | `octaves`, `sycl_initial_blur`, `sycl_contrast`, feature limit | Fixed five layers, no scale-up; shared `intervals`, `sigma` and `edge_threshold` do not configure this implementation. |
| OpenCV CPU | `intervals`, `sigma`, `opencv_contrast`, `edge_threshold`, feature limit | Automatic octave count (`octaves_automatic:1`); requested `octaves` is not applied. |

`sycl_layers_fixed:5` and `sycl_scale_up:0` describe SYCL only, even when present
in another backend's file. Synthetic transform, photometric and blur options do
not alter independent input images. OpenCV acceleration is disabled and the
configured CPU thread count is used. No backend equivalence or timing qualification
is implied by a successful export.

All 11 local tests pass. The scorer/export suite also passes on Arc for all three
enabled backends, including textured identity with positive inliers, precision 1
and RMSE 0; empty output; metadata/matrix contracts; rejected resize settings,
unsupported backend, unreadable image and oversized dimensions. Security review
of the modified code path found no additional artifact fix. This remains an offline
diagnostic for vetted images/configuration, not an untrusted upload API: OpenCV
decodes before the dimension check and extraction precedes the output-count check;
these limits do not bound decoder, parser or extraction peak resource consumption.
Protect exported image features and file paths according to the source data policy.

The first real-viewpoint plumbing check uses OpenCV's native 800x640 `graf1.png`
and `graf3.png`, with `H1to3p.xml` (`H13`), associated by its AKAZE sample.
OpenCV source commit: `e7c8ba4dfd2c8ada9562ca95a50afff077c4307e`.
Both images were canonicalized with ImageMagick grayscale/depth 8, without resizing,
then hashed with configuration and geometry before extraction. OpenCL, SYCL and
OpenCV ran on Arc; pinned unmodified CudaSift
`ed5ef54c67354959e3d5fa829d30de5b278b4d62` ran on RTX 5060 with the same four-octave,
initial-blur-1, contrast-3, no-scale-up reference settings. All outputs were scored
by the common ratio-0.8 / known-homography-3-pixel evaluator, without RANSAC.

| Backend | Inliers / ratio matches | Precision | Inlier RMSE (px) | Distinct inlier source / target positions |
| --- | --- | --- | --- | --- |
| OpenCL | 229 / 332 | 68.98% | 1.345735 | 208 / 203 |
| SYCL | 302 / 489 | 61.76% | 1.412982 | 290 / 271 |
| OpenCV | 388 / 668 | 58.08% | 1.196355 | 364 / 358 |
| CudaSift | 308 / 521 | 59.12% | 1.400583 | 295 / 281 |

These are different accepted correspondence sets, not common-match localization
errors. No overlap mask, spatial clustering or one-to-one assignment was added.
Graf influenced prior tuning, so this is explicitly **not held-out** and cannot
establish general application quality. No throughput claim follows from these runs.
The CudaSift quality floor is still unmet; backend selection and Python remain blocked.
The official Oxford wall archive acquisition failed TLS certificate verification;
no certificate checks or trust settings were weakened and no dataset was accepted.
Next: acquire verified, separate held-out known-homography pairs before evaluating
without further tuning; investigate the existing quality and SYCL repeatability gaps.

Durable workspace evidence: `results/20261102/viewpoint-smoke-summary.json`,
`viewpoint-smoke/INPUTS.sha256`, the raw `viewpoint-smoke` archive and
`viewpoint-smoke-receipts.sha256`. Arc extraction stage
`independent-export-8d339ce711a8dd9f`, manifest
`8d339ce711a8dd9f6bfea5091dfc32cca1396476492fb1e3f6c719dbcccb35eb`;
final guard stage `export-guards-4cd4566d95ac4a6d`, manifest
`4cd4566d95ac4a6dc496d70a61c6708e835d316c38149843b43813c8a2b0e18b`.
CUDA stage `graf-viewpoint-3aa531a897965409`; local raw copies
`/tmp/sift-independent-export-results.cmyCJO` and `/tmp/sift-graf-cuda.XtrKpe`.

## Projective Scoring and Rejected Scale Probe

Checkpoint 46 retains diagnostic/scorer changes only. Extraction remains exactly
checkpoint 45, including its default parameters and quality deficits.

A tested half-layer gradient-selection probe changed grouping from
`round(local.scale)` to `round(local.scale + 0.5)`, consistent with the nearest
Gaussian to the recorded midpoint DoG sigma. Independent sigma-based host
reconstruction passed, but both complete 64-case Arc runs regressed on identical
pairs. Distinct inlier source support decreased in 37 default and 44 dense cases;
precision decreased in 35 and 43. Default CUDA count/precision/RMSE deficits became
26/7/5, and dense 2/11/4. The probe and its proposed test contract were reverted;
the restored refinement suite passes. Nearest-sigma selection is not evidence that
the existing lower-Gaussian gradient convention is incorrect. No speed claim was
made for this rejected candidate.

The external scorer now accepts either the existing `affine` float64 2x3 matrix
or a `homography` float64 3x3 matrix, never both. This allows independently known
perspective geometry without estimating a transform from the tested matches:

```json
{
  "width": 640,
  "height": 480,
  "homography": {
    "type_id": "opencv-matrix", "rows": 3, "cols": 3, "dt": "d",
    "data": [1.0, 0.0, 10.0, 0.0, 1.0, 20.0, 0.001, 0.0, 1.0]
  }
}
```

```bash
validate_sift_pair --score-external first-features.json second-features.json \
  geometry.json scored.json
```

Geometry maps exported first-image pixel coordinates to second-image coordinates.
Both feature files must match the declared dimensions; adjust the matrix for any
resize/crop before scoring. The existing dimension and feature-cap bounds remain.
Use decimal/exponent notation for double coefficients: large bare integer literals
failed homogeneous-scale tests with this OpenCV FileStorage reader, despite `dt:d`.
Pair files are limited to 1 MiB; matrix shape/type/data length are checked before
allocation. Projective matrices are normalized by their maximum coefficient magnitude,
checked for finite normalized values, and rejected when numerically rank-deficient
using SVD. No division by `H[2,2]` is assumed, so valid matrices with that entry zero
are supported. The input coefficient scale is not a quality-tuning parameter.

Scoring divides by the homogeneous coordinate. A zero or numerically cancelling
denominator, or a nonfinite projected position, increments
`unprojectable_ratio_matches`. These matches remain in `ratio_matches`, contribute
no inlier, and therefore cannot inflate precision by disappearing. All reports now
include this count (zero for ordinary affine scoring); external reports also include
`geometry_model`. The ratio threshold stays 0.8 and inlier radius stays 3 pixels.
No RANSAC, overlap mask, spatial clustering or one-to-one assignment was added.

Tests cover analytic perspective, positive/negative homogeneous scaling including
1e-100 and 1e100, affine-as-homography, valid zero-bottom-right matrices, the exact
3-pixel boundary and a just-outside match, horizon points, malformed/ambiguous/missing
matrices, singular/numerically singular matrices, oversized pair files, and all prior
scorer cases. All 11 local tests and the final Arc scorer suite pass. Input review
found no remaining issue in the modified bounded geometry path; pre-existing external
feature limits remain in force.

Compatibility checks rescored all 64 frozen CUDA exports and regenerated the 64
default Arc cases. CUDA, OpenCL and OpenCV preserve all prior counts, spatial-support
metrics and precision exactly. Residual arithmetic is not bit-identical: maximum
absolute difference is 9.79e-15 pixels for CUDA, 6.26e-15 for OpenCL and 9.75e-15 for
OpenCV. The separate 1e-12-pixel arithmetic compatibility check is not a tolerance
for accepting lower product quality. Frozen reference scores were not overwritten.

SYCL has non-roundoff differences in 33/64 comparisons. Repeating the previous
unchanged binary on the combined baboon pair yields 330-331 inliers and 341-342
ratio matches; the new binary shows the same ranges. OpenCL remains at 362 inliers
through these repeats. This establishes pre-existing SYCL repeatability variability,
not its root cause or general harmlessness. SYCL determinism/eligibility remains an
open gate; exact all-backend compatibility is not claimed.

Evidence in the SIFT workspace: `results/20261102/scale-association-{cases,summary}.json`,
`homography-affine-compatibility.json`, `homography-arc-compatibility.json`, raw report
archives and `homography-receipts.sha256`. Rejected probe payload
`/tmp/sift-scale-association.iljTBm`, Arc stage `scale-association-09a6a5ffe564202e`,
manifest `09a6a5ffe564202e4c361145d136103a31d3a2b0b144ff018cbe6a2b7530d50b`;
reports `/tmp/sift-scale-association-results.R1gKX9`. Affine corpus stage
`homography-efdd579c3b140aec`, reports `/tmp/sift-homography-results.sHHQJo`;
CUDA rescores `/tmp/sift-homography-affine-compat.uhThkF`. Final guard/test stage
`homography-final-31da384a6377bbf5`, manifest
`31da384a6377bbf5d7fe3802b33e59077740efa3d9c3e82bc12369eb5be132eb`,
payload `/tmp/sift-homography-final.BXfEJd`, test/repeatability reports
`/tmp/sift-homography-repeatability.953u6r`. No extraction changes followed the
affine compatibility run; the final follow-up only added a projective normalization
guard and a numerical-singularity test.

Checkpoint 47 subsequently adds independent-image exports and a development-only
viewpoint check, as documented above. A separate held-out dataset, CudaSift-level
quality, backend selection, lifecycle/recovery qualification and Python remain open.

## Spatial Support and Exact Duplicates

Checkpoint 45 removes exact duplicate localized extrema within each OpenCL octave,
before the feature cap, orientation assignment and descriptor generation. Neighboring
seeds can converge to identical x/y/scale records during iterative refinement.
A first-occurrence set preserves output order; distinct scales, octaves and legitimate
multiple orientations remain. No distance tolerance, response threshold or matcher
rule changes. The raw candidate-refinement API retains its per-candidate behavior.

A deterministic 1025x769 noise fixture reproduced two duplicates among 1695 points
before the fix. Four sigma/interval configurations now verify unique localized
points and exact host/resident ordering and response parity. Existing cross-octave,
orientation, descriptor and capacity tests remain enabled. All 11 local tests pass;
the expanded refinement and scoring suites also pass on Arc.

The common scorer now adds these diagnostics without changing its matching rules:

- `first_distinct_positions`, `second_distinct_positions`: distinct float x/y pairs.
- `first_duplicate_records`, `second_duplicate_records`: records beyond the first
  with equal x/y and all 128 equal descriptor values. Colocated but different
  descriptors are not duplicate records.
- `inlier_distinct_first_positions`, `inlier_distinct_second_positions`: distinct
  source/target positions participating in accepted ground-truth inliers.

These are exact numeric-equality counts, not spatial clustering, one-to-one matching,
overlap-adjusted recall or unique physical landmark counts. Nearby detections may
still represent the same scene point. Scorer tests cover identical queries, identical
targets, different descriptors at the same position, many-to-one matches and empty
outputs, alongside the existing malformed-input checks. Reporting runs outside the
timed extraction. It allocates temporary sets proportional to feature count; existing
external-input bounds and validation remain unchanged.

Before extraction changes, both 64-case configurations were rerun with the new
reporting: every existing OpenCL score remained exactly unchanged. All 64 frozen
CUDA exports were rescored locally and their prior scores also remained unchanged.
CUDA extraction/settings were not rerun or changed. Exact duplicate records appeared
in all 64 OpenCL cases and 33 CUDA cases. Then both OpenCL configurations were rerun
with deduplication on byte-identical frozen pairs. All OpenCL duplicate-record counts
became zero. Distinct inlier source and target support never decreased in any case.

| Diagnostic | Default configuration | Experimental dense configuration |
| --- | --- | --- |
| Cases with increased distinct source support | 55 / 64 | 64 / 64 |
| Cases with lower raw inlier counts | 16 / 64 | 10 / 64 |
| Cases with lower precision | 22 / 64 | 19 / 64 |
| Remaining CUDA count / precision / RMSE deficits | 25 / 3 / 5 | 1 / 9 / 4 |
| Remaining CUDA distinct source / target support deficits | 27 / 26 | 1 / 2 |

Removing repeated queries can reduce raw counts, while removing identical target
competitors makes additional ratio matches eligible, including outliers. This is
not a universal precision gain. Dense blurred building has 524 distinct inlier
target positions versus CUDA's 527; blurred graf has 550 versus 585 (source support
584 versus 600). The stricter CudaSift quality requirement remains unmet. Default
parameters remain unchanged; dense sigma 1.0/five intervals remains nondefault.

Unprofiled Arc A/B/B/A timing, two fresh processes per build/configuration and
30 measured samples per process, gives the following pooled median isolated
first-image extraction times. Both binaries include the same reporting code.

| Fixture | Defaults before -> after (ms) | Dense before -> after (ms) |
| --- | --- | --- |
| Box | 4.668 -> 4.625 | 5.164 -> 5.285 |
| Building | 5.879 -> 5.959 | 8.091 -> 8.872 |
| Graf | 6.257 -> 6.402 | 7.941 -> 8.594 |

Default deltas range from about -1% to +2.3%; dense is about 2-10% slower. This is
diagnostic sampling, not release performance qualification or application latency.
The dense configuration's quality and latency tradeoffs prevent its promotion.

Evidence in the SIFT workspace: `results/20261102/spatial-support-cases.json`,
`dedup-cases.json`, `dedup-summary.json`, `dedup-timing.json`, and the corresponding
raw-report archives and `dedup-receipts.sha256`. Baseline-reporting payload
`/tmp/sift-spatial-support.2xzagy`, Arc stage `spatial-support-a178577778696fc5`,
manifest `a178577778696fc59759d262ed47c1f26ea522592fb792c7634b27361fc59c6b`,
reports `/tmp/sift-spatial-support-results.AotN5D`. Deduplication payload
`/tmp/sift-dedup.SKozWg`, Arc stage `dedup-11e3ba0a8d748968`, manifest
`11e3ba0a8d7489687930d644fc0114c5c870f0b34079dd481495ec58e003cd27`,
reports `/tmp/sift-dedup-results.35arsX`. Both stages are under the existing
user-space staging root. Frozen CUDA exports remain unmodified.

Next: blur/scale localization and scale-space differences, then independent held-out
real-viewpoint pairs with known geometry. The present affine scorer cannot establish
general perspective homography accuracy. No backend selection or Python work yet.

## Bounded Refinement Follow-up

Checkpoint 44 retains five-fit neighboring-sample relocation in OpenCL refinement.
The former one-fit implementation discarded a detected coupled quadratic maximum
at (8, 7) whose continuous peak is (8.6, 7.25, 2.1). Relocation recovers that peak
without changing contrast, spatial-edge, finite-value or interior-bound checks.
Each unsuccessful fit moves at most one sample per axis; boundary escape or five
unsuccessful fits reject the candidate. Both host and resident refinement use the
same helper. Defaults remain sigma 1.6 and three scale intervals.

All 11 local tests pass, including analytic recovery, iteration exhaustion, boundary
escape and preserved contrast/edge rejection. The expanded refinement test also
passes on Arc. Existing resident/host, orientation, descriptor and capacity tests
remain enabled. This intentionally changes feature counts, not merely throughput.

Two configurations completed all 64 cases on Arc: current defaults with relocation,
and an experimental sigma-1.0/five-interval configuration. Every generated first
and second PGM was compared byte-for-byte to the frozen corpus. CudaSift records
and scoring rules were unchanged. A nine-case sigma-1.0/three-interval probe
preceded the dense configuration. Neither experiment changes product defaults.
The validator's shared sigma/interval settings also change its OpenCV diagnostic;
comparisons here use the original frozen reference records, not that changed output.

Each entry is median inlier count / pooled inlier RMSE in pixels:

| Profile | Previous OpenCL | Relocation, defaults | Relocation, dense | Frozen CudaSift |
| --- | --- | --- | --- | --- |
| Identity | 704.5 / 0 | 828 / 0 | 4484.5 / 0 | 617 / 0 |
| Rotation 30 | 357.5 / 0.310 | 495 / 0.320 | 2450 / 0.445 | 329.5 / 0.846 |
| Rotation 90 | 476.5 / 0.154 | 589 / 0.194 | 3127.5 / 0.263 | 304.5 / 0.672 |
| Scale 0.5 | 95.5 / 0.258 | 129.5 / 0.277 | 977.5 / 0.389 | 119 / 0.718 |
| Scale 1.5 | 185 / 0.394 | 263.5 / 0.426 | 1304.5 / 0.573 | 175 / 1.197 |
| Illumination | 614.5 / 0.075 | 723 / 0.074 | 3072 / 0.094 | 107 / 0.273 |
| Blur | 272.5 / 0.724 | 352.5 / 0.803 | 591 / 0.800 | 114 / 0.893 |
| Rotation + scale | 254 / 0.374 | 363 / 0.398 | 2006.5 / 0.482 | 247.5 / 0.928 |

Defaults gain inliers in all 64 cases versus previous OpenCL, but precision is lower
in 7 cases and RMSE higher in 41. These are different accepted correspondence sets;
the result is not a universal improvement in localization. Against CudaSift, defaults
still have 25 count deficits, 3 precision deficits and 5 RMSE deficits. Dense has
1 count deficit (blurred graf: 669 versus 691), 9 precision deficits and 4 RMSE
deficits. These deficit counts overlap. Dense blur pooled precision is 81.54% versus
CudaSift's 84.14%. Higher feature density alone does not establish quality parity.
No numerical acceptance tolerance or exception has been approved.

Unprofiled Arc A/B/B/A timing used two fresh processes per build/configuration and
30 samples per process, pooled to 60 samples. Baseline is checkpoint 43. The timed
operation is the validator's isolated OpenCL extraction on the first image, not
two extractions plus matching or end-to-end application latency.

| Fixture | Defaults before -> after (ms) | Dense before -> after (ms) |
| --- | --- | --- |
| Box | 4.527 -> 4.613 | 5.004 -> 5.251 |
| Building | 5.664 -> 5.866 | 7.474 -> 8.081 |
| Graf | 6.049 -> 6.254 | 7.366 -> 8.004 |

Default latency increased about 2-4% on these fixtures. This is diagnostic timing,
not the release sampling gate, a new full-resolution throughput claim, or evidence
of superiority to complete-gpu-sift. The denser configuration increases latency
and output volume further and remains experimental.

Evidence: payload `/tmp/sift-cuda-quality-floor.fz2w8I`; Arc stage
`~/.local/share/sift-extractor-staging/cuda-quality-floor-9b6a01f6165d86b2`;
manifest `9b6a01f6165d86b2621234ed2f8079830004b31a2ce43369d6c02e1341c5c431`;
downloaded reports `/tmp/sift-cuda-quality-floor-results.wuoXTe`;
SIFT workspace receipts `results/20261102/cuda-quality-floor-cases.json`,
`cuda-quality-floor-summary.json` and `cuda-quality-floor-timing.json`.
The final source differs from the measured snapshot only by loop indentation,
verified with `diff -w`; focused compilation/runtime validation was repeated.

Next: investigate precision/localization on the failing blur and scale cases,
including correspondence duplication and scale-space differences, without changing
the frozen CUDA baseline or silently weakening the matcher. Add unique spatial
coverage and independently known real-viewpoint/occlusion geometry before declaring
application quality eligibility. This development corpus has now influenced tuning;
a separate held-out corpus is required. Backend selection and Python remain blocked
on quality and the existing lifecycle/concurrency/recovery gates.

## Historical Five-way Baseline

2026-11-02: all 64 cases completed for **all five implementations**. OpenCV CPU,
OpenCL, SYCL and complete-gpu-sift ran on the Arc host; pinned CudaSift ran on the
RTX 5060 after SSH authentication was restored. All 128 CUDA input images and
64 pair reports are byte-identical to the saved Arc inputs. CUDA features were
returned to the same local evaluator for matching and ground-truth scoring.
This completes a five-way diagnostic, not production quality qualification or
backend selection. This work changes diagnostic tools, not extraction kernels.

## Protocol

Eight distinct OpenCV sample images: aloeL.jpg, baboon.jpg, box.png, building.jpg,
fruits.jpg, graf1.png, leuvenA.jpg and sudoku.png. Original files and their hashes
are retained in the payload. All were converted with ImageMagick
`convert INPUT -colorspace Gray -depth 8 OUTPUT.pgm`; tool version is recorded.
The portable OpenCV build could not decode JPEG, so the first mixed-format run
failed 40 cases. It is not included in the successful results below. Every source
was canonicalized, and the complete 64-case matrix was rerun, not just failures.

Images retain aspect ratio, bounded to 640x480 without upscaling. Eight fixed
profiles are applied about the image center: identity; 30-degree rotation;
90-degree rotation; 0.5x scale; 1.5x scale; intensity gain 0.6 plus bias 20;
Gaussian blur sigma 2; and 30-degree rotation plus 0.85x scale. Affine warping uses
linear interpolation and constant-zero borders. Blur uses OpenCV's default border
handling; photometric conversion saturates to uint8. Exact first/second PGM files
and affine matrices are saved. Cropping/occlusion from the transforms is retained.

Every backend uses the same decoded grayscale pair. Matching is one-way CPU
BFMatcher L2, strict Lowe ratio below 0.8, with ground-truth reprojection error at
most 3 pixels defining inliers. RANSAC is not used. Counts are correspondences,
not unique scene landmarks or true recall. There is no common-overlap mask or
one-to-one assignment, and multiple orientations can yield multiple matches.
RMSE concerns each backend's own accepted inliers; it is not error on a shared
correspondence set. No-match RMSE is -1 in individual reports and null in aggregates.

Settings are frozen before the run, **not equivalent**: OpenCV 4.10 uses three
octave layers, contrast 0.04, edge 10, sigma 1.6; OpenCL uses four octaves, three
intervals, contrast 1.0, sigma 1.6 and Hessian ratio limit 12.1; SYCL uses four
octaves, its fixed five layers, initial blur 1.0, contrast 3.0 and no scale-up.
All three request unlimited features; SYCL capacity is 32768. CudaSift commit
`ed5ef54c67354959e3d5fa829d30de5b278b4d62` uses four octaves, initial blur 1.0,
contrast 3.0, no scale-up and capacity 32768. It was built with CUDA 13.2.51,
GCC 15.2, `sm_120` and its original `--use_fast_math -O3 -lineinfo` flags, against
OpenCV 4.10. The RTX 5060 driver is 595.99.02; no CUDA export reached capacity.
The unchanged
complete-gpu-sift algorithm has its native 10000-point cap and settings. No case
reached that cap. No quality-dependent threshold tuning or algorithm repairs were
performed. These are sample-image stress tests, not an independent held-out
benchmark, real-viewpoint dataset or production acceptance corpus.

## Results

Each cell is **median inlier count / pooled inlier RMSE in pixels** across eight
images. Medians average the two central values. Pooled RMSE weights squared errors
by each case's inlier count, and must be read alongside counts and match precision.

| Transform | OpenCV | OpenCL | SYCL | CudaSift | complete-gpu-sift |
| --- | --- | --- | --- | --- | --- |
| Identity | 1735.5 / 0 | 704.5 / 0 | 624.5 / 0 | 617 / 0 | Median 0; six cases have no inliers |
| Rotation 30 | 951 / 0.301 | 357.5 / 0.310 | 325 / 0.846 | 329.5 / 0.846 | 0 / undefined |
| Rotation 90 | 1368 / 0.513 | 476.5 / 0.154 | 306.5 / 0.675 | 304.5 / 0.672 | 0 / undefined |
| Scale 0.5 | 325.5 / 0.303 | 95.5 / 0.258 | 120 / 0.702 | 119 / 0.718 | 0 / undefined |
| Scale 1.5 | 545 / 0.424 | 185 / 0.394 | 171.5 / 1.190 | 175 / 1.197 | 0 / undefined |
| Illumination | 604 / 0.059 | 614.5 / 0.075 | 108 / 0.269 | 107 / 0.273 | 0 / undefined |
| Blur | 152 / 0.805 | 272.5 / 0.724 | 116 / 0.897 | 114 / 0.893 | 0 / undefined |
| Rotation + scale | 827.5 / 0.316 | 254 / 0.374 | 247 / 0.927 | 247.5 / 0.928 | 0 / undefined |

All eight identity cases have precision 1 and zero localization error for OpenCV,
OpenCL, SYCL and CudaSift. All four produce inliers in all 64 cases. For combined
rotation and scale, pooled match precision is OpenCV 90.52%, OpenCL 86.93%, SYCL 88.60%,
CudaSift 87.96%.

OpenCL has substantial correspondence-count gaps versus OpenCV on geometric
transformations, but more median inliers under this blur and illumination test.
SYCL and CudaSift have higher pooled localization error than OpenCL on every
non-identity profile. Their aggregated quality metrics are close, but not identical;
this is not bitwise parity. OpenCL's half-scale median inlier count is lower than
both, so there is no universal winner. These observations do not establish
parameter-matched algorithm rankings or quality-qualified speedups.

complete-gpu-sift has zero inliers in all 56 non-identity cases and six of eight
identity cases. On the Arc box-image identity case, 774 features contain only five
distinct descriptor vectors. Its kernel declares one `__local float hist[128]`
shared by work-items that process different keypoints, with no isolated histogram
per keypoint. Descriptor duplication and the identity failures are consistent with
this code defect; no repaired-reference performance or quality is inferred.
The shared ratio test correctly rejects ambiguous equal-distance neighbors.
Thus our implementations outperform this particular reference build on these
tested transformations, but its throughput is not a quality-equivalent target.

## Historical Baseline Reproduction

Build with the existing Intel/OpenCV comparison configuration and optionally set
`SIFT_COMPLETE_REFERENCE_SOURCE` to the benchmark copy of complete-gpu-sift's C++
source. This only builds a diagnostic exporter; no reference code is installed in
the library. The source copy differs from the original in platform selection and
benchmark application behavior, not extraction kernels. Build targets are
`validate_sift_pair` and `export_complete_sift`.

```bash
bash scripts/run_quality_corpus.sh build/validate_sift_pair \
  build/export_complete_sift /path/to/canonical-pgm-corpus new-results
```

The runner refuses an existing output directory, records every failed execution
and returns nonzero on any failure. It writes per-case results plus aggregate
`cases.json` and `summary.json` only when all cases complete. Optional trailing
profile names select a focused smoke run. It does not collect timing samples.

`validate_sift_pair IMAGE REPORT 0 CONFIG quality-export` saves exact pairs and
the three existing backend reports. `--score-external FIRST.json SECOND.json
PAIR_REPORT.json OUTPUT.json` scores external exports with the same function,
without initializing GPUs. Export matrices are float32 Nx2 positions and Nx128
descriptors, accompanied by image dimensions and capacity metadata. The importer
rejects invalid shapes, nonfinite data, zero descriptors and out-of-image points.
The CUDA exporter branch is selected with `SIFT_VALIDATE_CUDA` and linked against
the pinned CudaSift reference. The existing SIFT workspace build recipe
`results/20261101/cuda-reference-build/CMakeLists.txt` accepts
`SIFT_QUALITY_EXPORT_SOURCE` pointing to `benchmarks/export_reference.cpp` and builds
`export_cuda_sift`. A fresh source extraction from the verified pinned archive was
used, leaving the prior reference build untouched. Run the exporter separately on
each saved PGM, then use `--score-external` for each pair. The exporter records
device, CUDA compile/driver API versions, extraction settings and capacity status.

All 11 local tests pass, including known-transform scorer checks, empty outputs
and five malformed-input cases. The scorer tests also pass on Arc. The legacy
default-transform OpenCL quality record is unchanged.
The fresh CUDA build passes all three native extraction/matching/homography tests.
Its independent box-image identity smoke exports yield 624 accepted matches,
all inliers with zero reprojection error. All 128 full-corpus exports pass the
shared importer's finite/nonzero/shape/bounds validation and all 64 pairs score.

## Evidence

- Parent extraction checkpoint: `2b68b3a1f`.
- Payload: `/tmp/sift-quality-pgm-corpus.fbFScZ`.
- Remote Arc stage: `~/.local/share/sift-extractor-staging/quality-pgm-f0bfe8705a662086`.
- Manifest SHA256: `f0bfe8705a66208678436f5dbe49115449e32c35f3c3342ed406a6bd7421f77a`.
- Retrieved reports and exact pairs: `/tmp/sift-quality-pgm-results.l7DcWH/results`.
- SIFT workspace receipts: `results/20261102/quality-corpus-cases.json`,
  `quality-corpus-summary.json`, and `quality-reference-metadata.json`.
- Raw reference descriptors remain in the remote stage, including failed identity
  cases. Canonical and original image hashes and reference source snapshot are kept.
- The post-run aggregate-writing addition to the runner was validated separately
  on an identity smoke run; the full matrix used the same extraction/scoring code.
- CUDA payload and returned exports: `/tmp/sift-cuda-quality.kLne8P`.
- NVIDIA stage: `~/.local/share/sift-extractor-staging/sift-cuda-quality.kLne8P`.
- CUDA pair manifest SHA256: `52b9c5c0a96dfcbc7cbfe24cc8d7fd3bebdcee9b6dd095791539893d359bccfd`.
- Exporter/source receipt SHA256: `f42d9a4f1956c0822c067a831e8da140c35486d0cd70a01528cd31d74de3654b`.
- Returned export manifest SHA256: `977015dfe6715b08f05f4e8f6fad04f2a6d1269e2c1435e83d92df3f71f6bca7`.
- Five-way receipts in the SIFT workspace: `results/20261102/quality-cuda-cases.json`,
  `quality-fiveway-cases.json` and `quality-fiveway-summary.json`. Cases are joined
  by exact image/profile, rejecting missing or duplicate CUDA cases; all 40
  backend/profile aggregates have eight cases. The older four-way receipts remain.

Next: expand to real viewpoint/occlusion pairs with independently known geometry,
compare parameter and feature-density effects, and establish quality eligibility
before selecting the product backend. No production recovery/concurrency, held-out
corpus or cross-device qualification gate is implied by these results.