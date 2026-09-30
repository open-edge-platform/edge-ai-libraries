<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: multimodal-embedding-serving-user

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T09:03:33Z  
**Evals**: 1, 2, 3, 4, 5 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 0 / 5 | 5 / 5 | **+5 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 33% ±33% | 100% ±0% | **+67pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 102 s | 159 s | +57 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 137k | 540k | +403k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Get Intel's multimodal embedding service running locally with the CLIP/clip-vit-... | PASS (3/3) | FAIL (0/3) |
| 2 | The embedding service is running on localhost:9777 with CLIP/clip-vit-b-32. Show... | PASS (2/2) | FAIL (0/2) |
| 3 | The embedding service is running on localhost:9777 with CLIP/clip-vit-b-32. Give... | PASS (3/3) | FAIL (2/3) |
| 4 | Image requests to my embedding service return HTTP 400, but text requests work. ... | PASS (3/3) | FAIL (2/3) |
| 5 | Use the multimodal embedding service to give me a text summary of this warehouse... | PASS (3/3) | FAIL (1/3) |
| | **Mean ±σ** | **100% ±0%** | **33% ±33%** |