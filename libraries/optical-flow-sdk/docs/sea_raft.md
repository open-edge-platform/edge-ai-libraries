<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# SEA-RAFT-S (P2 Slow accuracy tier)

Plan gate (§8 quality / §10 P2): SEA-RAFT-S KITTI train Fl-all ≤ NVOFA Medium
(published Ada Medium Fl-all **19.11%**).

## Status (2026-11-10)

| Item | Status |
|------|--------|
| Quality gate (KITTI train 200 Fl-all) | **PASS** — **2.70%** vs 19.11% (`benchmarks/results/p2_sea_raft_kitti_fl_all_2026-11-10.json`) |
| Measurement path | PyTorch SEA-RAFT-S HF weights on CPU (`scripts/eval_sea_raft_kitti.py`) |
| OpenVINO IR export | Done on lab (`sea_raft_s_384x1248.{xml,bin}`) via `scripts/export_sea_raft_openvino.py` |
| C++ `Algorithm::SeaRaft` | OpenVINO Runtime loader (gray→RGB replicate; resize to model HxW) |
| iGPU FPS claim | **Not yet** — measure with `OPTICALFLOW_SEA_RAFT_DEVICE=GPU` after OV GPU plugin OK |

Model: `MemorySlices/Tartan-C-T-TSKH-kitti432x960-S` + `config/eval/kitti-S.json`.

## Lab setup

```bash
# OpenVINO toolkit (C++) already at ~/intel/openvino_toolkit_* on labrat
source ~/intel/openvino_toolkit_*/setupvars.sh

cmake -S . -B build-ov -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_CPU=ON -DOPTICALFLOW_ENABLE_OPENCL=ON \
  -DOPTICALFLOW_ENABLE_OPENVINO=ON \
  -DOpenVINO_DIR=$HOME/intel/openvino_toolkit_*/runtime/cmake

export OPTICALFLOW_SEA_RAFT_MODEL=$HOME/models/sea-raft/openvino/sea_raft_s_384x1248.xml
export OPTICALFLOW_SEA_RAFT_DEVICE=GPU   # or CPU

# Quality reproduce (micromamba env sea-raft + ~/src/SEA-RAFT):
python scripts/eval_sea_raft_kitti.py \
  --kitti ~/datasets/optical-flow --sea-raft ~/src/SEA-RAFT --device cpu
```

Export IR (fixed shape):

```bash
python scripts/export_sea_raft_openvino.py \
  --sea-raft ~/src/SEA-RAFT --out-dir ~/models/sea-raft/openvino \
  --height 384 --width 1248
```
