<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-summarize-video

**Agents**: Copilot (`claude-sonnet-5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-25T06:42:41Z  
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
| Copilot (`claude-sonnet-5`) | 8% ±17% | 100% ±0% | **+92pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 238 s | 244 s | +6 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 1734k | 1565k | -169k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Prepare an offline API sequence to summarize an already ingested VSS video with ... | PASS (3/3) | FAIL (0/3) |
| 2 | Build the summary request for video id `warehouse-88`: title it `Warehouse morni... | PASS (3/3) | FAIL (0/3) |
| 3 | For VSS video id `yard-cam-17`, document a summary request that skips the final ... | PASS (3/3) | FAIL (1/3) |
| 4 | Explain the offline Pipeline Manager sequence for summarizing an already uploade... | PASS (3/3) | FAIL (0/3) |
| | **Mean ±σ** | **100% ±0%** | **8% ±17%** |