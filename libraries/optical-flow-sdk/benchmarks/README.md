<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmarks

- `microbench_cpu` — synthetic CPU preset timings (no dataset).
- `eval_flow_epe` — banded EPE; synthetic by default, or `--gt/--pred` `.flo`.
- `compare_opencv_dis` — optional OpenCV DIS diagnostic (adapter ON).

Lab harnesses for full Sintel / KITTI / Spring timing and OpenCV parity remain
for GPU backends. Protocol and gates: see `../PLAN.md` §8.
Named SKUs: Core Ultra Series 2 iGPU + Arc B580.

Example with Middlebury/Sintel `.flo` pairs once downloaded:

```bash
./build/eval_flow_epe --gt /data/sintel/flow/xxx.flo --pred /tmp/pred.flo
```
