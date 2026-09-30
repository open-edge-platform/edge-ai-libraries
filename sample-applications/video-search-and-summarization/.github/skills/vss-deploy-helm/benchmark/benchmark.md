<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-deploy-helm

**Agents**: Copilot (`claude-sonnet-5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-25T06:46:03Z  
**Evals**: 1, 2, 3, 4 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 1 / 4 | 4 / 4 | **+3 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 58% ±42% | 100% ±0% | **+42pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 306 s | 197 s | -109 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 1544k | 1125k | -419k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Prepare an offline installation plan for VSS summary mode with OVMS in namespace... | PASS (3/3) | PASS (3/3) |
| 2 | Document how to replace an existing unified VSS Helm release named `vss` with du... | PASS (3/3) | FAIL (2/3) |
| 3 | Write an offline values example for VSS summary mode using OVMS with a VLM on an... | PASS (3/3) | FAIL (2/3) |
| 4 | Prepare a Helm command and user-values checklist for unified VSS with the Xeon v... | PASS (3/3) | FAIL (0/3) |
| | **Mean ±σ** | **100% ±0%** | **58% ±42%** |