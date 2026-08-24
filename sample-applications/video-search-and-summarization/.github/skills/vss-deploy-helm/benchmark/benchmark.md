<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-deploy-helm

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
| Copilot (`claude-sonnet-5`) | 20% ±0% | 100% ±0% | **+80pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 173 s | 134 s | -39 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 124k | 720k | +596k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I have a fresh Kubernetes cluster with `kubectl` and Helm 3 already working, and... | PASS (5/5) | FAIL (1/5) |
| 2 | I currently have the `vss` release running in unified mode (`unified_summary_sea... | PASS (5/5) | FAIL (1/5) |
| 3 | My nodes have Intel GPUs and NPUs available via device plugins. For my VSS summa... | PASS (5/5) | FAIL (1/5) |
| 4 | I want to install VSS in unified mode with vLLM as the backend instead of OVMS, ... | PASS (5/5) | FAIL (1/5) |
| | **Mean ±σ** | **100% ±0%** | **20% ±0%** |
