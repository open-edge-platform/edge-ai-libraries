<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CUDA Reference Checkpoint

The standalone build in `benchmarks/cuda_reference` builds the pinned CudaSift
algorithm and its existing tests without changing that source or adding CUDA to
the production library. It bypasses the upstream build's hardcoded Ada target.

## Reproduce

Export CudaSift commit `ed5ef54c67354959e3d5fa829d30de5b278b4d62` into a fresh
directory, including its committed data fixtures and MIT license. Do not copy a
modified working tree or old build outputs. From this component directory:

```bash
cmake -S benchmarks/cuda_reference -B build-cuda-reference \
  -DCUDASIFT_REFERENCE_SOURCE=/path/to/pinned-export \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_COMPILER=/path/to/cuda/bin/nvcc \
  -DCMAKE_CUDA_ARCHITECTURES=120 \
  -DOpenCV_DIR=/path/to/opencv/lib/cmake/opencv4
cmake --build build-cuda-reference --parallel 4
ctest --test-dir build-cuda-reference --verbose --output-on-failure
```

For flattened CUDA redistributable archives, also pass
`-DCMAKE_CUDA_FLAGS=-L/path/to/cuda/lib` so nvcc can find cudart_static/cudadevrt.
Choose the architecture for the actual GPU; 120 is the verified RTX 5060 target.
C++17 and the original CUDA --use_fast_math/-O3/-lineinfo options are retained.
The recipe does not download sources, install packages or change the GPU driver.

## Verified Configuration

Verified 2026-11-01: RTX 5060 (compute capability 12.0), NVIDIA open driver
595.99.02, private CUDA 13.2.51, GCC 15.2.0, CMake 3.31.6 and OpenCV 4.10.0.
OpenCV modules: core, imgproc, imgcodecs, highgui, features2d and calib3d, with
CUDA/OpenCL/IPP acceleration disabled. PNG/PGM loading is enabled; GUI is disabled.
CUDA 13.2 supports GCC 15 and R595, but its qualification table predates Ubuntu
26.04. This configuration is experimentally validated, not officially OS-qualified.

| Test | Result |
| --- | --- |
| cuda_reference.extract | 10 assertions passed, 0 failed |
| cuda_reference.match | 11 assertions passed, 0 failed |
| cuda_reference.homography | 8 assertions passed, 0 failed |

All 3/3 tests passed. Basic PNG extraction produced 1911 features; repeated sorted
positions matched 1911/1911. Thresholds 1/3/5/10 produced 7081/1911/542/6 features.
The stereo PGM test reported 1453/2084 features, 754 RANSAC matches and 675 refined
inliers. Existing cudaMemcpyToArray deprecation warnings remain in the reference.

## Provenance and Limits

The exported source archive SHA256 was
`6eb352340b8dd0cc9c4df51dddd8012527fbe77976386d9775b5aee3eab8a0f3`.
The left.pgm fixture SHA256 was
`92ffdb4b2c0d6ee81544c026e42c2368187f625a0aa256083ebbca22fe0c7b98`.
The img1.png fixture SHA256 was
`a712af5da93d7ba8e373f4fc191240c02bfabc4c9d865381fec593477cd20db8`.

These are reference-test results, not a CUDA/OpenCL/SYCL quality noninferiority
comparison. RANSAC inliers are not known ground truth. Legacy speed assertions and
printed timings do not establish matched or hardware-normalized performance.
Shared transformed-pair scoring with recorded settings remains the next gate.