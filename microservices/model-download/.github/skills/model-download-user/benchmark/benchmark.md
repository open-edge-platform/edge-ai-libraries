<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: model-download-user

**Agents**: Copilot (`claude-sonnet-4-6`)  
**Grader**: Copilot (`claude-sonnet-5.5`)  
**Date**: 2026-11-02T05:14:48Z  
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-4-6`) | 1 / 8 | 8 / 8 | **+7 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-4-6`) | 65% ±26% | 100% ±0% | **+35pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-4-6`) | 47 s | 47 s | -0 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-4-6`) | 0 | 0 | +0 ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I need meta-llama/Llama-3.2-1B from HuggingFace for a local experiment. I alread... | PASS (5/5) | PASS (5/5) |
| 2 | I want sentence-transformers/all-MiniLM-L6-v2 from HuggingFace for a reproducibl... | PASS (5/5) | FAIL (1/5) |
| 3 | I need the meta-llama/Llama-3.2-1B model converted to OpenVINO format for a loca... | PASS (5/5) | FAIL (2/5) |
| 4 | I want to get llama3.2:3b through the model-download service for local use inste... | PASS (5/5) | FAIL (4/5) |
| 5 | I need yolov8n prepared with INT8 quantization for an edge demo. Please show me ... | PASS (5/5) | FAIL (3/5) |
| 6 | I want the HLS 3D pose model for a healthcare analytics prototype. Please show m... | PASS (5/5) | FAIL (4/5) |
| 7 | I have a trained model in Intel Geti and want to fetch it with this service for ... | PASS (5/5) | FAIL (3/5) |
| 8 | I’m brand new to this repo. Please show me how to get the model-download service... | PASS (5/5) | FAIL (4/5) |
| | **Mean ±σ** | **100% ±0%** | **65% ±26%** |