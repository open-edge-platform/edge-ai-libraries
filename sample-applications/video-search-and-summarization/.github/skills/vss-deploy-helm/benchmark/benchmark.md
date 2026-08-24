<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-deploy-helm

**Agents**: Claude (`claude-sonnet-5`)
**Grader**: Claude (`claude-sonnet-5`)
**Date**: 2026-08-23T05:52:32Z
**Evals**: 1, 2, 3, 4 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 1 / 4 | 4 / 4 | **+3 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 45% ±53% | 100% ±0% | **+55pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 970 s | 251 s | -719 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Claude (`claude-sonnet-5`) | 4132k | 1092k | -3040k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Claude (w/) | Claude (w/o) |
|---|---|---|---|
| 1 | I have a fresh Kubernetes cluster with `kubectl` and Helm 3 working, and I want ... | PASS (5/5) | FAIL (4/5) |
| 2 | I want to run VSS in search-only mode on my cluster - the Helm equivalent of `se... | PASS (5/5) | FAIL (0/5) |
| 3 | My nodes have Intel GPUs and NPUs available via device plugins. For my VSS summa... | PASS (5/5) | PASS (5/5) |
| 4 | I'm on a fresh machine - the VSS source isn't checked out anywhere and I'm not i... | PASS (5/5) | FAIL (0/5) |
| | **Mean ±σ** | **100% ±0%** | **45% ±53%** |
