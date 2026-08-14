<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vdms-dataprep-user

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T09:10:26Z  
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
| Copilot (`claude-haiku-4.5`) | 10% ±22% | 100% ±0% | **+90pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 140 s | 193 s | +53 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 141k | 517k | +376k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | Give me an exact runbook to start Intel's VDMS dataprep stack (dataprep API, vec... | PASS (4/4) | FAIL (0/4) |
| 2 | The vdms dataprep service is healthy on localhost:6007. Give me the exact reques... | PASS (3/3) | FAIL (0/3) |
| 3 | In bucket vdms-bucket, video_id dp_video_1730000000 is already ingested. Give me... | PASS (2/2) | FAIL (0/2) |
| 4 | My 2 GB MP4 gets HTTP 413 when sent toward the dataprep upload endpoint. Diagnos... | PASS (2/2) | FAIL (1/2) |
| 5 | In bucket vdms-bucket, video directory dp_video_1730000000 contains forklift.mp4... | PASS (2/2) | FAIL (0/2) |
| | **Mean ±σ** | **100% ±0%** | **10% ±22%** |