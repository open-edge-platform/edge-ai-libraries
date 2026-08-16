<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-deploy-helm

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T09:17:35Z  
**Evals**: 1, 2, 3, 4, 5, 6, 90 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 0 / 7 | 1 / 7 | **+1 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 3% ±8% | 57% ±31% | **+54pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 176 s | 238 s | +62 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 195k | 1009k | +813k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I have a fresh Kubernetes cluster with `kubectl` and Helm 3 already working, and... | FAIL (3/5) | FAIL (1/5) |
| 2 | I currently have the `vss` release running in unified mode (`unified_summary_sea... | FAIL (3/5) | FAIL (0/5) |
| 3 | My nodes have Intel GPUs and NPUs available via device plugins. For my VSS summa... | FAIL (4/5) | FAIL (0/5) |
| 4 | I want to run VSS in search-only mode on my cluster (equivalent to `setup.sh --s... | PASS (5/5) | FAIL (0/5) |
| 5 | I uninstalled and reinstalled the `vss` Helm release in namespace `vss-deploymen... | FAIL (2/5) | FAIL (0/5) |
| 6 | I uninstalled and reinstalled the `vss` Helm release in namespace `vss-deploymen... | FAIL (3/5) | FAIL (0/5) |
| 90 | I want to install VSS in unified mode with vLLM as the backend instead of OVMS, ... | FAIL (0/5) | FAIL (0/5) |
| | **Mean ±σ** | **57% ±31%** | **3% ±8%** |