<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: chatqna-helm-deploy

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T08:42:45Z  
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 1 / 12 | 10 / 12 | **+9 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 18% ±33% | 95% ±11% | **+77pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 258 s | 382 s | +124 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 330k | 1515k | +1185k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Deploy chatqna core to kubernetes with helm. I did not pick runtime or device. | PASS (4/4) | FAIL (0/4) |
| 2 | Install OpenVINO GPU profile with Helm in namespace ai. | PASS (5/5) | FAIL (1/5) |
| 3 | Deploy chatqna with ollama runtime using helm and set device gpu. | FAIL (3/4) | FAIL (0/4) |
| 4 | Translate these compose vars to helm overrides and deploy: BACKEND=openvino DEVI... | PASS (6/6) | FAIL (0/6) |
| 5 | Before deploy, run preflight and ensure namespace rag exists. | PASS (4/4) | FAIL (0/4) |
| 6 | Use OCI chart source version 1.3.3 for chatqna core and deploy to namespace ai. | PASS (4/4) | FAIL (0/4) |
| 7 | After install, provide hard evidence that deployment is healthy. | PASS (4/4) | FAIL (0/4) |
| 8 | Give me the access URLs and cleanup command after deployment. | PASS (3/3) | FAIL (0/3) |
| 9 | helm template failed due to invalid gpu key. What should the skill do? | PASS (3/3) | FAIL (2/3) |
| 10 | Pods are not Ready after helm install. Give me the failure workflow. | PASS (4/4) | PASS (4/4) |
| 11 | Health endpoint is returning 503 after deploy. | PASS (3/3) | FAIL (0/3) |
| 12 | PVC is stuck pending and storage is too small. | FAIL (2/3) | FAIL (1/3) |
| | **Mean ±σ** | **95% ±11%** | **18% ±33%** |