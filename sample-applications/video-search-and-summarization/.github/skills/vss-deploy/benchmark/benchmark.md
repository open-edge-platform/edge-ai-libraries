<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-deploy

**Agents**: Copilot (`claude-sonnet-5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-25T06:48:21Z  
**Evals**: 1, 2, 3, 4 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 2 / 4 | 4 / 4 | **+2 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 83% ±19% | 100% ±0% | **+17pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 212 s | 342 s | +130 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 1702k | 2107k | +404k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I am preparing a machine for VSS summary mode, but I do not want to start servic... | PASS (3/3) | FAIL (2/3) |
| 2 | Audit the VSS dual-UI configuration without launching containers. Show the confi... | PASS (3/3) | PASS (3/3) |
| 3 | Prepare commands for a unified VSS deployment on port 18080. I need one command ... | PASS (3/3) | PASS (3/3) |
| 4 | Document the single VSS command that resets application data after testing. Expl... | PASS (3/3) | FAIL (2/3) |
| | **Mean ±σ** | **100% ±0%** | **83% ±19%** |