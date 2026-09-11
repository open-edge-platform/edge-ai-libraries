<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: time-series-analytics-user

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`claude-haiku-4.5`)  
**Date**: 2026-08-26T09:18:13Z  
**Evals**: 1, 2, 3, 4, 5 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 1 / 5 | 5 / 5 | **+4 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 52% ±40% | 100% ±0% | **+48pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 409 s | 620 s | +211 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 1547k | 3864k | +2317k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Build a UDF that flags hydraulic pressure readings outside a safe operating band... | PASS (7/7) | FAIL (2/7) |
| 2 | Build a UDF that detects sudden vibration spikes on a motor and publishes an MQT... | PASS (8/8) | FAIL (4/8) |
| 3 | I have a UDF named `temp_alert` — the files `udfs/temp_alert.py` and `tick_scrip... | PASS (4/4) | PASS (4/4) |
| 4 | My MQTT alert is not working. I deployed a temperature UDF successfully — POST /... | PASS (3/3) | FAIL (0/3) |
| 5 | Build a UDF that uses a pre-trained scikit-learn IsolationForest model file `pum... | PASS (5/5) | FAIL (4/5) |
| | **Mean ±σ** | **100% ±0%** | **52% ±40%** |