<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-search-index

**Agents**: Copilot (`claude-sonnet-5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-25T06:44:34Z  
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
| Copilot (`claude-sonnet-5`) | 8% ±16% | 100% ±0% | **+92pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 189 s | 190 s | +1 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 957k | 1038k | +81k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Give me an offline API plan to upload `/data/cameras/receiving-bay.mp4` to VSS w... | PASS (3/3) | FAIL (0/3) |
| 2 | Construct an offline Pipeline Manager request that searches for `forklift near a... | PASS (3/3) | FAIL (0/3) |
| 3 | Explain how to search VSS for `white delivery van` and print real source filenam... | PASS (3/3) | FAIL (1/3) |
| 4 | A video named `north-gate-evening.mp4` is already uploaded. Document how to loca... | PASS (3/3) | FAIL (0/3) |
| | **Mean ±σ** | **100% ±0%** | **8% ±17%** |