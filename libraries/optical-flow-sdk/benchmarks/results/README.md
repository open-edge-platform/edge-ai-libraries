<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmark results (agent / P2 baseline)

| File | Role |
|------|------|
| `p1_opencv_dis_parity_baseline.json` | Frozen P1 Sintel/KITTI vs OpenCV DIS numbers + agent instructions for P2 |

## For agents starting P2

1. Read `p1_opencv_dis_parity_baseline.json` (and `PLAN.md` §10 P2 / §11.6).
2. Do **not** treat classical DIS as §8-pass; baseline is honest **FAIL**.
3. After accuracy changes, re-run `parity_opencv_datasets` with the same
   methodology fields in the JSON and record a new dated file beside this one
   (do not overwrite the P1 baseline).
4. SEA-RAFT P2 quality gate is vs **NVOFA Medium Fl-all**, not vs this
   OpenCV DIS pairwise table — still re-measure KITTI/Sintel for reporting.

Narrative tables: `../../PLAN.md` §11.6.
