<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: dlsps-user

**Agents**: Copilot (`claude-opus-4.6`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-26T12:27:50Z  
**Evals**: 1, 2 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-opus-4.6`) | 0 / 2 | 2 / 2 | **+2 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-opus-4.6`) | 72% ±21% | 100% ±0% | **+28pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-opus-4.6`) | 105 s | 69 s | -36 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-opus-4.6`) | 428k | 367k | -61k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Run object detection on a local video file using CPU and stream the results via ... | PASS (8/8) | FAIL (7/8) |
| 2 | Set up GPU-accelerated inference on a video stream and publish detection metadat... | PASS (7/7) | FAIL (4/7) |
| | **Mean ±σ** | **100% ±0%** | **72% ±21%** |