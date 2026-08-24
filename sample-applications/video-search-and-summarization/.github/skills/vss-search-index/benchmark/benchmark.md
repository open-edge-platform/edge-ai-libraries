<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-search-index

**Agents**: Claude (`claude-sonnet-5`)
**Grader**: Claude (`claude-sonnet-5`)
**Date**: 2026-08-24T04:04:55Z
**Evals**: 1, 2, 3, 4 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 0 / 4 | 4 / 4 | **+4 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 0% ±0% | 100% ±0% | **+100pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 763 s | 140 s | -623 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 1895k | 444k | -1451k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Claude (w/) | Claude (w/o) |
|---|---|---|---|
| 1 | I recorded a clip from the loading dock camera and saved it at `/home/intel/vide... | PASS (5/5) | FAIL (0/5) |
| 2 | I need to find forklift activity that happened indoors in the last 7 days - sear... | PASS (5/5) | FAIL (0/5) |
| 3 | Run a search for "delivery truck backing up" across all my videos - but I need t... | PASS (5/5) | FAIL (0/5) |
| 4 | I'm on a fresh box - the VSS application source isn't checked out anywhere and I... | PASS (5/5) | FAIL (0/5) |
| | **Mean ±σ** | **100% ±0%** | **0% ±0%** |
