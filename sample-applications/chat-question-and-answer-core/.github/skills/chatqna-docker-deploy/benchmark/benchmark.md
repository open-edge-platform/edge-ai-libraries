<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: chatqna-docker-deploy

**Agents**: Copilot (`claude-sonnet-5`)
**Grader**: Copilot (`gpt-5.3-codex`)
**Date**: 2026-08-26T04:22:50Z
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
| Copilot (`claude-sonnet-5`) | 28% ±39% | 100% ±0% | **+72pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 313 s | 282 s | -31 s ↑ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 382k | 1382k | +1000k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Deploy chatqna core with docker compose. I did not provide runtime or device. | PASS (5/5) | FAIL (0/5) |
| 2 | Deploy OpenVINO GPU profile for chatqna with docker compose. | PASS (4/4) | FAIL (0/4) |
| 3 | Deploy chatqna with ollama backend using docker compose. | PASS (4/4) | FAIL (0/4) |
| 4 | Deploy chatqna with prebuilt images. What should I export before deploy? | PASS (5/5) | FAIL (0/5) |
| 5 | Run preflight checks for docker deployment first. | PASS (3/3) | PASS (3/3) |
| 6 | After startup, provide readiness evidence for chatqna docker deployment. | PASS (4/4) | FAIL (0/4) |
| 7 | After the container is up, how to access ChatQ&A UI and API docs? | PASS (2/2) | FAIL (0/2) |
| 8 | Stop chatqna deployment and provide proof containers are terminated. | PASS (3/3) | FAIL (2/3) |
| 9 | setup_env.sh returned an unsupported backend or device value. | PASS (4/4) | FAIL (1/4) |
| 10 | Containers failed to start after docker compose up. Provide troubleshooting workflow. | PASS (3/3) | PASS (3/3) |
| 11 | Health endpoint is failing right after startup. What needs to be checked? | PASS (4/4) | FAIL (1/4) |
| 12 | Deploy with a custom model config and Hugging Face token for gated model access. | PASS (4/4) | FAIL (1/4) |
| | **Mean ±σ** | **100% ±0%** | **28% ±39%** |
