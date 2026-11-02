<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Broader Quality Diagnostic

## Status

The product quality requirement is **at least as good as CudaSift**, not 95% of
its correspondence count. This requirement is not yet demonstrated. OpenCV remains
a diagnostic reference. complete-gpu-sift is excluded from further acceptance work
and will not be repaired; its results below are historical evidence only.

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