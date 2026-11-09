<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# SEA-RAFT-S (P2 Slow accuracy tier)

Plan gate (§8 quality / §10 P2): SEA-RAFT-S via OpenVINO under `Preset::Slow`
or `Algorithm::SeaRaft`, measured KITTI train Fl-all ≤ NVOFA Medium on Core
Ultra Series 2 iGPU.

## Status

- API surface: `optical_flow_sdk/sea_raft.hpp`, `Algorithm::SeaRaft`.
- OpenVINO load/infer: **stub** until Runtime is linked
  (`-DOPTICALFLOW_ENABLE_OPENVINO=ON`) and a model path is supplied.
- Classical DIS quality retune (OpenCL Fast/Medium) is tracked separately in
  `benchmarks/results/p2_opencv_dis_parity_2026-11-10.json`.

## Enable on lab

```bash
# Install OpenVINO Runtime (C++), then:
cmake -S . -B build-ov -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_CPU=ON -DOPTICALFLOW_ENABLE_OPENCL=ON \
  -DOPTICALFLOW_ENABLE_OPENVINO=ON \
  -DOpenVINO_DIR=/path/to/openvino/runtime/cmake

export OPTICALFLOW_SEA_RAFT_MODEL=/path/to/sea_raft_s.xml   # or .onnx
```

Use `OpticalFlow(Backend::Auto, Preset::Slow, Algorithm::SeaRaft)` once the
loader is implemented. Until then construction throws with this guidance —
do not publish Fl-all claims.
