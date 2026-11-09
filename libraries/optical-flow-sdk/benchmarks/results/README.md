<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmark results (agent / P2 baseline)

| File | Role |
|------|------|
| `p1_opencv_dis_parity_baseline.json` | Frozen P1 Sintel/KITTI vs OpenCV DIS + agent instructions |
| `p2_opencv_dis_parity_2026-11-10.json` | P2 classical DIS retune (clamps + Fast propagate); §8 still FAIL |
| `p2_sea_raft_kitti_fl_all_2026-11-10.json` | P2 SEA-RAFT-S KITTI Fl-all **PASS** (2.70% ≤ 19.11%) |

## For agents continuing P2

1. Read both JSON files and `PLAN.md` §10 P2 / §11.6 / `docs/sea_raft.md`.
2. Classical DIS is still §8 **FAIL**, but P2 OpenCL Fast/Medium EPE improved
   vs P1; keep resident ≥10× when retuning further.
3. After accuracy changes, re-run `parity_opencv_datasets` and add a **new**
   dated JSON (do not overwrite P1 or prior P2 files).
4. SEA-RAFT gate is vs **NVOFA Medium Fl-all** (`Algorithm::SeaRaft` stub +
   `-DOPTICALFLOW_ENABLE_OPENVINO=ON`). Farneback/PyrLK OpenCL ports remain open.

Narrative tables: `../../PLAN.md` §11.6.
