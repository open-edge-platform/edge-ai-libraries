<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: model-download-user

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T09:00:39Z  
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 3 / 8 | 5 / 8 | **+2 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 52% ±47% | 90% ±15% | **+38pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 237 s | 261 s | +24 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 498k | 1121k | +622k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I need meta-llama/Llama-3.2-1B from HuggingFace for a local experiment. I alread... | PASS (5/5) | PASS (5/5) |
| 2 | I want sentence-transformers/all-MiniLM-L6-v2 from HuggingFace for a reproducibl... | FAIL (4/5) | FAIL (0/5) |
| 3 | I need the meta-llama/Llama-3.2-1B model converted to OpenVINO format for a loca... | PASS (5/5) | FAIL (1/5) |
| 4 | I want to get llama3.2:3b through the model-download service for local use inste... | FAIL (3/5) | FAIL (0/5) |
| 5 | I need yolov8n prepared with INT8 quantization for an edge demo. Please show me ... | PASS (5/5) | FAIL (4/5) |
| 6 | I want the HLS 3D pose model for a healthcare analytics prototype. Please show m... | FAIL (4/5) | FAIL (1/5) |
| 7 | I have a trained model in Intel Geti and want to fetch it with this service for ... | PASS (5/5) | PASS (5/5) |
| 8 | I’m brand new to this repo. Please show me how to get the model-download service... | PASS (5/5) | PASS (5/5) |
| | **Mean ±σ** | **90% ±15%** | **52% ±47%** |