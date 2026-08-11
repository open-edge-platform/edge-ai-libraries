<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-search-index

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T09:21:22Z  
**Evals**: 1, 2, 3, 4, 5, 6, 90 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 1 / 7 | 5 / 7 | **+4 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 20% ±38% | 89% ±23% | **+69pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 156 s | 207 s | +51 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 221k | 861k | +640k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I just recorded a clip from the loading dock camera and saved it at `/home/intel... | PASS (5/5) | FAIL (0/5) |
| 2 | Search my video library for "person wearing a hat" and show me the top matching ... | PASS (5/5) | PASS (5/5) |
| 3 | I need to find any forklift activity that happened indoors in the last 7 days. S... | PASS (5/5) | FAIL (0/5) |
| 4 | I uploaded a video yesterday but searches never return anything from it - I thin... | FAIL (4/5) | FAIL (2/5) |
| 5 | Run a search for "delivery truck backing up" across all my videos, but this time... | PASS (5/5) | FAIL (0/5) |
| 6 | I want an ongoing alert for "worker without a safety vest" across the warehouse ... | PASS (5/5) | FAIL (0/5) |
| 90 | I just uploaded a new clip from the parking lot camera called `lot_cam_2026-07-2... | FAIL (2/5) | FAIL (0/5) |
| | **Mean ±σ** | **89% ±23%** | **20% ±38%** |