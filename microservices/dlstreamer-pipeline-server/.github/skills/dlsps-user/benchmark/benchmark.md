<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: dlsps-user

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T08:48:30Z  
**Evals**: 1, 2 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 0 / 2 | 1 / 2 | **+1 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 31% ±44% | 93% ±10% | **+62pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 331 s | 65 s | -267 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 29k | 303k | +274k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Run object detection on a local video file using CPU and stream the results via ... | PASS (8/8) | FAIL (5/8) |
| 2 | Set up GPU-accelerated inference on a video stream and publish detection metadat... | FAIL (6/7) | FAIL (0/7) |
| | **Mean ±σ** | **93% ±10%** | **31% ±44%** |