<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: chatqna-helm-deploy

**Agents**: Copilot (`claude-sonnet-5`)
**Grader**: Copilot (`gpt-5.3-codex`)
**Date**: 2026-08-26T05:14:33Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 2 / 12 | 12 / 12 | **+10 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 28% ±38% | 100% ±0% | **+72pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 496 s | 594 s | +98 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 382k | 2110k | +1727k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Deploy chatqna core to kubernetes with helm. I did not pick runtime or device. | PASS (4/4) | FAIL (0/4) |
| 2 | Install OpenVINO GPU profile with Helm in namespace ai. | PASS (5/5) | FAIL (2/5) |
| 3 | Deploy chatqna with ollama runtime using helm and set device gpu. | PASS (4/4) | FAIL (0/4) |
| 4 | Translate these compose vars to helm overrides and deploy: BACKEND=openvino DEVI... | PASS (6/6) | FAIL (1/6) |
| 5 | Before deploy, run preflight and ensure namespace rag exists. | PASS (4/4) | FAIL (2/4) |
| 6 | Use OCI chart source version 2026.2.0-rc2-helm for chatqna core and deploy to namespace ai. | PASS (4/4) | FAIL (0/4) |
| 7 | After install, provide hard evidence that deployment is healthy. | PASS (4/4) | FAIL (0/4) |
| 8 | Give me the access URLs and cleanup command after deployment. | PASS (3/3) | FAIL (0/3) |
| 9 | helm template failed due to invalid gpu key. What should the skill do? | PASS (3/3) | PASS (3/3) |
| 10 | Pods are not Ready after helm install. Give me the failure workflow. | PASS (4/4) | PASS (4/4) |
| 11 | Health endpoint is returning 503 after deploy. | PASS (3/3) | FAIL (0/3) |
| 12 | PVC is stuck pending and storage is too small. | PASS (3/3) | FAIL (1/3) |
| | **Mean ±σ** | **100% ±0%** | **28% ±38%** |