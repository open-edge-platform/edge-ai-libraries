<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmarks

- `microbench_cpu` — synthetic CPU preset timings (no dataset).
- `eval_flow_epe` — banded EPE; synthetic by default, or `--gt/--pred` `.flo`.
- `compare_opencv_dis` — optional OpenCV CPU parity diagnostic (adapter ON):
  DIS-Fast, Farneback, and sparse PyrLK vs OpenCV on a textured synthetic
  shift (GT-EPE + pairwise EPE + wall ms). Pass `--strict` to fail on soft
  SDK GT-EPE ceilings used by CI.

Lab harnesses for full Sintel / KITTI / Spring timing and honest OpenCV DIS
disparity remain for named SKUs / GPU backends. Protocol and gates: see
`../PLAN.md` §8. Named SKUs: Core Ultra Series 2 iGPU + Arc B580.

Example with Middlebury/Sintel `.flo` pairs once downloaded:

```bash
./build/eval_flow_epe --gt /data/sintel/flow/xxx.flo --pred /tmp/pred.flo
```
