<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: multimodal-dataprep-user

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-10-27T04:22:01Z  
**Evals**: 1, 2, 3, 4, 5, 6 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 0 / 6 | 6 / 6 | **+6 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 26% ±25% | 100% ±0% | **+74pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 219 s | 213 s | -5 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 0 | 0 | +0 ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Give me an exact runbook to start Intel Multimodal DataPrep with the default pre... | PASS (4/4) | FAIL (1/4) |
| 2 | I want Multimodal DataPrep to store vectors in Milvus while keeping raw media in... | PASS (3/3) | FAIL (1/3) |
| 3 | The service is healthy on localhost:6007. Give me the exact request to ingest /d... | PASS (3/3) | FAIL (0/3) |
| 4 | Show me how to ingest https://example.com/camera.jpg as a remote image and tag i... | PASS (2/2) | FAIL (0/2) |
| 5 | Delete the ingested media item video-summary/dp_video_1730000000 and its embeddi... | PASS (3/3) | FAIL (2/3) |
| 6 | I mounted a camera drop directory into the DataPrep container. Submit it as an a... | PASS (3/3) | FAIL (1/3) |
| | **Mean ±σ** | **100% ±0%** | **26% ±25%** |