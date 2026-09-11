<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: chatqna-troubleshoot

**Agents**: Copilot (`claude-sonnet-5`)
**Grader**: Copilot (`gpt-5.3-codex`)
**Date**: 2026-08-26T08:36:03Z
**Evals**: 1, 2, 3 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 0 / 3 | 3 / 3 | **+3 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 60% ±35% | 100% ±0% | **+40pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 91 s | 180 s | +89 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 97k | 877k | +780k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | My ChatQnA deployment starts, but POST /v1/chatqna/chat returns 500. I am using OpenVINO on CPU with Docker Compose. Please troubleshoot and give exact checks and fixes. | PASS (5/5) | FAIL (1/5) |
| 2 | I deployed with Helm and the UI URL does not load. Pods are running in namespace ai-demo. Help me debug and isolate whether this is nginx/service/nodeport related. | PASS (5/5) | FAIL (4/5) |
| 3 | Document upload fails with 400 and sometimes 500 in ChatQnA. Show me how to troubleshoot request format vs backend ingestion/model errors. | PASS (5/5) | FAIL (4/5) |
| | **Mean ±σ** | **100% ±0%** | **60% ±35%** |
