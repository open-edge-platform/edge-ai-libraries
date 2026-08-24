<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-search-index

**Agents**: Copilot (`claude-sonnet-5`)
**Grader**: Copilot (`gpt-5.3-codex`)
**Date**: 2026-08-24T06:38:03Z
**Evals**: 1, 2, 3, 4 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 0 / 4 | 4 / 4 | **+4 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 0% ±0% | 100% ±0% | **+100pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 89 s | 315 s | +226 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 145k | 1577k | +1433k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I just recorded a clip from the loading dock camera and saved it at `/home/intel... | PASS (5/5) | FAIL (0/5) |
| 2 | I need to find any forklift activity that happened indoors in the last 7 days. S... | PASS (5/5) | FAIL (0/5) |
| 3 | Run a search for "delivery truck backing up" across all my videos, but this time... | PASS (5/5) | FAIL (0/5) |
| 4 | I just uploaded a new clip from the parking lot camera called `lot_cam_2026-07-2... | PASS (5/5) | FAIL (0/5) |
| | **Mean ±σ** | **100% ±0%** | **0% ±0%** |
