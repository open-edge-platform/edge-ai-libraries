<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: time-series-analytics-user

**Agents**: Copilot (`claude-sonnet-5`)  
**Grader**: Copilot (`claude-sonnet-5`)  
**Date**: 2026-08-25T13:28:58Z  
**Evals**: 1, 2, 3 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 1 / 3 | 3 / 3 | **+2 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 73% ±35% | 100% ±0% | **+27pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 466 s | 406 s | -60 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 4222k | 3998k | -224k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Build a UDF that flags hydraulic pressure readings outside a safe operating band... | PASS (6/6) | FAIL (2/6) |
| 2 | Build a UDF that detects sudden vibration spikes on a motor and publishes an MQT... | PASS (7/7) | FAIL (6/7) |
| 3 | Deploy a pretrained anomaly-detection model for wind turbine sensor data through... | PASS (5/5) | PASS (5/5) |
| | **Mean ±σ** | **100% ±0%** | **73% ±35%** |