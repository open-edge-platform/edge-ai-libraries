<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Broader Quality Diagnostic

## Status

2026-11-02: 64/64 Arc cases completed for OpenCV CPU, OpenCL, SYCL and
complete-gpu-sift. CudaSift is **pending**, not a zero result: batch-mode access to
the NVIDIA host failed authentication. Its export adapter branch is prepared but
has not yet been compiled or run. No five-way quality qualification or backend
selection is claimed. This work changes diagnostic tools, not extraction kernels.

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
All three request unlimited features; SYCL capacity is 32768. The unchanged
complete-gpu-sift algorithm has its native 10000-point cap and settings. No case
reached that cap. No quality-dependent threshold tuning or algorithm repairs were
performed. These are sample-image stress tests, not an independent held-out
benchmark, real-viewpoint dataset or production acceptance corpus.

## Results

Each cell is **median inlier count / pooled inlier RMSE in pixels** across eight
images. Medians average the two central values. Pooled RMSE weights squared errors
by each case's inlier count, and must be read alongside counts and match precision.

| Transform | OpenCV | OpenCL | SYCL | complete-gpu-sift |
| --- | --- | --- | --- | --- |
| Identity | 1735.5 / 0 | 704.5 / 0 | 624.5 / 0 | Median 0; six cases have no inliers |
| Rotation 30 | 951 / 0.301 | 357.5 / 0.310 | 325 / 0.846 | 0 / undefined |
| Rotation 90 | 1368 / 0.513 | 476.5 / 0.154 | 306.5 / 0.675 | 0 / undefined |
| Scale 0.5 | 325.5 / 0.303 | 95.5 / 0.258 | 120 / 0.702 | 0 / undefined |
| Scale 1.5 | 545 / 0.424 | 185 / 0.394 | 171.5 / 1.190 | 0 / undefined |
| Illumination | 604 / 0.059 | 614.5 / 0.075 | 108 / 0.269 | 0 / undefined |
| Blur | 152 / 0.805 | 272.5 / 0.724 | 116 / 0.897 | 0 / undefined |
| Rotation + scale | 827.5 / 0.316 | 254 / 0.374 | 247 / 0.927 | 0 / undefined |

All eight identity cases have precision 1 and zero localization error for OpenCV,
OpenCL and SYCL. All three produce inliers in all 64 cases. For rotation + scale,
pooled match precision is OpenCV 90.52%, OpenCL 86.93%, SYCL 88.60%.

OpenCL has substantial correspondence-count gaps versus OpenCV on geometric
transformations, but more median inliers under this blur and illumination test.
SYCL has higher pooled localization error than OpenCL on every non-identity
profile. These observations do not establish parameter-matched algorithm rankings.

complete-gpu-sift has zero inliers in all 56 non-identity cases and six of eight
identity cases. On the Arc box-image identity case, 774 features contain only five
distinct descriptor vectors. Its kernel declares one `__local float hist[128]`
shared by work-items that process different keypoints, with no isolated histogram
per keypoint. Descriptor duplication and the identity failures are consistent with
this code defect; no repaired-reference performance or quality is inferred.
The shared ratio test correctly rejects ambiguous equal-distance neighbors.
Thus our implementations outperform this particular reference build on these
tested transformations, but its throughput is not a quality-equivalent target.

## Reproduction

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
the pinned CudaSift reference; runtime validation remains pending authentication.

All 11 local tests pass, including known-transform scorer checks, empty outputs
and five malformed-input cases. The scorer tests also pass on Arc. The legacy
default-transform OpenCL quality record is unchanged.

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

Next: authenticate the NVIDIA host, build and test its adapter, process the saved
128 images with the pinned CudaSift build, and score them locally with the same
validator. Then expand to real viewpoint/occlusion pairs with independently known
geometry and establish quality eligibility before selecting the product backend.