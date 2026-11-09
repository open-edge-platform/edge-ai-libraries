<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmarks

- `microbench_cpu` — synthetic CPU preset timings (no dataset).
- `microbench_opencl` / `microbench_opencl_resident` — OpenCL host vs device-resident walls.
- `microbench_sycl` — SYCL timings (secondary backend).
- `eval_flow_epe` — banded EPE; synthetic by default, or `--gt/--pred` `.flo`.
- `compare_opencv_dis` — optional OpenCV CPU parity diagnostic (adapter ON):
  DIS-Fast, Farneback, and sparse PyrLK vs OpenCV on a textured synthetic
  shift (GT-EPE + pairwise EPE + wall ms). Pass `--strict` to fail on soft
  SDK GT-EPE ceilings used by CI.
- `parity_opencv_datasets` — honest OpenCV DIS disparity on MPI Sintel
  training + KITTI 2015 training (adapter ON). Protocol/gates: `../PLAN.md` §8.
- `results/p1_opencv_dis_parity_baseline.json` — frozen lab numbers + P2
  agent instructions (`results/README.md`).

## Dataset download (lab)

```bash
./scripts/fetch_datasets.sh ~/datasets/optical-flow
cmake --build build --target parity_opencv_datasets
./build/parity_opencv_datasets \
  --sintel ~/datasets/optical-flow --kitti ~/datasets/optical-flow \
  --backend cpu --preset medium
./build/parity_opencv_datasets \
  --sintel ~/datasets/optical-flow --kitti ~/datasets/optical-flow \
  --backend opencl --preset medium --max-pairs 50
```

SDK DIS is DIS-lite (no variational refinement). Pairwise EPE vs full OpenCV
DIS may fail the ≤0.05px / 2% bar — the tool reports PASS/FAIL honestly.
Named SKU: Core Ultra Series 2 iGPU.

```bash
./build/eval_flow_epe --gt /data/sintel/flow/xxx.flo --pred /tmp/pred.flo
```
