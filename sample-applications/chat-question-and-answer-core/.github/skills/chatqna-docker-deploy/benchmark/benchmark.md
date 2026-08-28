<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: chatqna-docker-deploy

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T08:36:47Z  
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 0 / 12 | 8 / 12 | **+8 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 10% ±21% | 87% ±22% | **+76pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 298 s | 311 s | +13 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 362k | 1125k | +763k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Deploy chatqna core with docker compose. I did not provide runtime or device. | PASS (4/4) | FAIL (0/4) |
| 2 | Deploy OpenVINO GPU profile for chatqna with docker compose. | PASS (4/4) | FAIL (0/4) |
| 3 | Deploy chatqna with ollama backend using docker compose. | PASS (4/4) | FAIL (0/4) |
| 4 | Use prebuilt images but I did not provide tags. What should I export before depl... | FAIL (3/4) | FAIL (0/4) |
| 5 | Run preflight checks for docker deployment first. | PASS (3/3) | FAIL (1/3) |
| 6 | After startup, provide readiness evidence for chatqna docker deployment. | PASS (4/4) | FAIL (0/4) |
| 7 | Give me the access URLs after successful docker compose deploy. | FAIL (2/3) | FAIL (0/3) |
| 8 | Stop chatqna deployment and provide proof containers are terminated. | FAIL (2/3) | FAIL (2/3) |
| 9 | setup_env.sh returned an unsupported backend or device value. How should this be... | PASS (3/3) | FAIL (0/3) |
| 10 | Containers failed to start after docker compose up. Provide troubleshooting work... | FAIL (1/3) | FAIL (0/3) |
| 11 | Health endpoint is failing right after startup. What should I check? | PASS (4/4) | FAIL (0/4) |
| 12 | Deploy with a custom model config and Hugging Face token for gated model access. | PASS (4/4) | FAIL (1/4) |
| | **Mean ±σ** | **87% ±22%** | **10% ±21%** |