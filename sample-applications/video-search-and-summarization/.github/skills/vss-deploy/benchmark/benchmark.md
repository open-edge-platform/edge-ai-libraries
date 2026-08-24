<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-deploy

**Agents**: Claude (`claude-sonnet-5`)
**Grader**: Claude (`claude-sonnet-5`)
**Date**: 2026-08-23T05:38:30Z
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
| Claude (`claude-sonnet-5`) | 224 s | 229 s | +6 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 964k | 1340k | +376k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Claude (w/) | Claude (w/o) |
|---|---|---|---|
| 1 | I just got a fresh box and want to try video summarization with VSS in summary m... | PASS (5/5) | FAIL (0/5) |
| 2 | Before I commit to anything I want to see what VSS in dual UI mode (summary and ... | PASS (5/5) | FAIL (0/5) |
| 3 | I'm planning a unified-mode VSS deployment - one UI where I can search over the ... | PASS (5/5) | FAIL (0/5) |
| 4 | I'm done testing VSS for today. I want the containers stopped and removed, and t... | PASS (5/5) | FAIL (0/5) |
| | **Mean ±σ** | **100% ±0%** | **0% ±0%** |
