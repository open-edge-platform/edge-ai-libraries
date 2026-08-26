<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: chatqna-run-unit-tests

**Agents**: Copilot (`claude-sonnet-5`)
**Grader**: Copilot (`gpt-5.3-codex`)
**Date**: 2026-08-26T09:09:01Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 1 / 12 | 11 / 12 | **+10 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 42% ±32% | 97% ±10% | **+56pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 236 s | 283 s | +47 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 405k | 1317k | +912k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I changed backend endpoints and UI components. Run unit tests. | PASS (4/4) | FAIL (3/4) |
| 2 | Run backend tests only for openvino runtime. | PASS (4/4) | FAIL (2/4) |
| 3 | Run backend unit tests for ollama runtime. | FAIL (2/3) | FAIL (1/3) |
| 4 | Run UI unit tests only. | PASS (4/4) | FAIL (1/4) |
| 5 | Run all unit tests with coverage. | PASS (3/3) | FAIL (0/3) |
| 6 | I changed app code, run tests, but skip UI. | PASS (3/3) | FAIL (0/3) |
| 7 | Run a targeted backend test file tests/test_server.py with openvino. | PASS (3/3) | FAIL (2/3) |
| 8 | Run only tests matching Conversation in UI. | PASS (3/3) | FAIL (0/3) |
| 9 | I changed code but do not run tests. | PASS (3/3) | FAIL (2/3) |
| 10 | uv is missing when trying to run backend tests. What should happen? | PASS (3/3) | PASS (3/3) |
| 11 | UI tests fail due to missing node_modules. | PASS (3/3) | FAIL (1/3) |
| 12 | Some tests are failing. Give me the result summary. | PASS (4/4) | FAIL (2/4) |
| | **Mean ±σ** | **97% ±10%** | **42% ±32%** |
