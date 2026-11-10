<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmark results (agent baselines)

| File | Role |
|------|------|
| `p1_opencv_dis_parity_baseline.json` | Frozen P1 Sintel/KITTI vs OpenCV DIS + agent instructions |
| `p2_opencv_dis_parity_2026-11-10.json` | P2 classical DIS retune (clamps + Fast propagate); §8 still FAIL |
| `p2_sea_raft_kitti_fl_all_2026-11-10.json` | P2 SEA-RAFT-S KITTI Fl-all **PASS** (2.70% ≤ 19.11%) |
| `p2_sea_raft_openvino_fps_2026-11-10.json` | P2 SEA-RAFT OpenVINO iGPU ~15.7 FPS @384×1248 |
| `p4_nvofa_rtx5060_2026-11-09.json` | P4 measured NVOFA on RTX 5060 (FPS @720p/1080p + KITTI Fl-all) |

## For agents (P2 exit met; P3/P4 comparative)

1. Read JSON files and `PLAN.md` §10 / §11.6–§11.7 / `docs/sea_raft.md`.
2. Classical DIS remains §8 **FAIL** (DIS-lite); SEA-RAFT closes the quality gate.
3. Prefer `calc_device` for ≥10× claims (`docs/backend-selection.md`).
4. OpenCL Farneback uses full poly expansion; soft vs OpenCV identity —
   `docs/farneback.md`. PyrLK OpenCL landed.
5. FRUC/warp: seed sample `sample_warp_with_flow`; see `docs/fruc_warp.md`.
6. After accuracy changes, add a **new** dated JSON (do not overwrite priors).

Narrative tables: `../../PLAN.md` §11.5–§11.6.
