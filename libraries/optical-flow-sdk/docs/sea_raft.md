<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# SEA-RAFT-S (P2 Slow accuracy tier)

Plan gate (§8 quality / §10 P2): SEA-RAFT-S KITTI train Fl-all ≤ NVOFA Medium
(published Ada Medium Fl-all **19.11%**).

## Status (2026-11-10+)

| Item | Status |
|------|--------|
| Quality gate (KITTI train 200 Fl-all) | **PASS** — **2.70%** vs 19.11% (`benchmarks/results/p2_sea_raft_kitti_fl_all_2026-11-10.json`) |
| Measurement path | PyTorch SEA-RAFT-S HF weights on CPU (`scripts/eval_sea_raft_kitti.py`) |
| OpenVINO IR export | Fixed-shape IRs via `scripts/export_sea_raft_openvino.py` |
| C++ `Algorithm::SeaRaft` | OpenVINO Runtime loader (gray→RGB replicate; resize to model HxW) |
| Primary iGPU FPS | **~15.7–16.6 FPS** @384×1248; **~20.2 FPS** @432×960 (`benchmarks/results/p2_sea_raft_openvino_fps_*.json`) |

Model family: `MemorySlices/Tartan-C-T-TSKH-kitti432x960-S` + `config/eval/kitti-S.json`.

## Preset mapping

| SDK `Preset` | Dense algorithm | SEA-RAFT? | Notes |
|--------------|-----------------|-----------|-------|
| `Fast` | DIS (CPU/OpenCL/SYCL) | No | Classical speed path; ≥10× via OpenCL `calc_device` |
| `Medium` | DIS | No | Higher DIS quality dial |
| `Slow` | DIS by default | **Opt-in** | Use `Algorithm::SeaRaft` explicitly for neural Slow tier |

```cpp
// Neural Slow accuracy tier (requires OPTICALFLOW_ENABLE_OPENVINO + model env)
optical_flow_sdk::OpticalFlow of(
    optical_flow_sdk::Backend::Cpu,   // device comes from OpenVINO, not Backend
    optical_flow_sdk::Preset::Slow,
    optical_flow_sdk::Algorithm::SeaRaft);
```

Env:

| Variable | Meaning |
|----------|---------|
| `OPTICALFLOW_SEA_RAFT_MODEL` | Path to OpenVINO `.xml` (fixed NCHW shape) |
| `OPTICALFLOW_SEA_RAFT_DEVICE` | `GPU` (Series 2 iGPU) or `CPU` |

## Resolutions / IR shapes

OpenVINO export is **fixed-shape**. Pick an IR that matches (or pad/resize into)
your pipeline resolution:

| IR file | H×W | Role |
|---------|-----|------|
| `sea_raft_s_384x1248.xml` | 384×1248 | **Lab primary FPS IR** (KITTI-width class); reported ~15.7 FPS iGPU |
| `sea_raft_s_432x960.xml` | 432×960 | Matches HF checkpoint name (`kitti432x960`); quality/eval shape |
| (custom) | any even H×W | `export_sea_raft_openvino.py --height H --width W` |

Notes:

- C++ `SeaRaftOpticalFlow` **resizes** host frames to the IR HxW before infer;
  flow is resized back to the input size.
- Wall FPS in JSON artifacts is **sync InferRequest only** (no decode/resize).
- Absolute 1080p FPS is not claimed for SEA-RAFT-S on Series 2 iGPU; use DIS
  Fast `calc_device` for ≥60@720p / ≥30@1080p classical gates.
- Literature ref: SEA-RAFT-S ~21 FPS @1080p on RTX 3090 (paper) — different
  device/resolution; not a Series 2 gate.

## FPS table (Series 2 iGPU)

| IR | Device | ms/pair | FPS | Artifact |
|----|--------|---------|-----|----------|
| 384×1248 | Arc iGPU | ~60–64 | **~15.7–16.6** | `p2_sea_raft_openvino_fps_2026-11-10.json` |
| 432×960 | Arc iGPU | ~49.4 | **~20.2** | `p2_sea_raft_openvino_fps_432x960_2026-11-10.json` |
| 384×1248 | CPU | ~872 | ~1.15 | same as first JSON |

Smaller IR (432×960) is faster; pick the IR that matches your pad/resize policy.

Re-bench additional IRs:

```bash
python scripts/bench_sea_raft_openvino.py \
  --model ~/models/sea-raft/openvino/sea_raft_s_384x1248.xml --device GPU
python scripts/bench_sea_raft_openvino.py \
  --model ~/models/sea-raft/openvino/sea_raft_s_432x960.xml --device GPU \
  --out-json benchmarks/results/p2_sea_raft_openvino_fps_432x960.json
```

## Lab setup

```bash
source ~/intel/openvino_toolkit_*/setupvars.sh

cmake -S . -B build-ov -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_CPU=ON -DOPTICALFLOW_ENABLE_OPENCL=ON \
  -DOPTICALFLOW_ENABLE_OPENVINO=ON \
  -DOpenVINO_DIR=$HOME/intel/openvino_toolkit_*/runtime/cmake

export OPTICALFLOW_SEA_RAFT_MODEL=$HOME/models/sea-raft/openvino/sea_raft_s_384x1248.xml
export OPTICALFLOW_SEA_RAFT_DEVICE=GPU

# Quality reproduce (micromamba env sea-raft + ~/src/SEA-RAFT):
python scripts/eval_sea_raft_kitti.py \
  --kitti ~/datasets/optical-flow --sea-raft ~/src/SEA-RAFT --device cpu
```

Export IR (fixed shape):

```bash
python scripts/export_sea_raft_openvino.py \
  --sea-raft ~/src/SEA-RAFT --out-dir ~/models/sea-raft/openvino \
  --height 384 --width 1248

python scripts/export_sea_raft_openvino.py \
  --sea-raft ~/src/SEA-RAFT --out-dir ~/models/sea-raft/openvino \
  --height 432 --width 960
```
