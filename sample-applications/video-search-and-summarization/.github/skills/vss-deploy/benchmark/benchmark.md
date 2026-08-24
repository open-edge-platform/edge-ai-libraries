<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-deploy

**Agents**: Copilot (`claude-sonnet-5`)
**Grader**: Copilot (`gpt-5.3-codex`)
**Date**: 2026-08-24T06:38:03Z
**Evals**: 1, 2, 3, 4 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 0 / 4 | 4 / 4 | **+4 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 0% ±0% | 100% ±0% | **+100pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 357 s | 292 s | -65 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 760k | 1960k | +1200k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I just cloned the video-search-and-summarization sample app and want to try vide... | PASS (5/5) | FAIL (0/5) |
| 2 | Before I commit to anything, I want to see which Docker Compose files and profil... | PASS (5/5) | FAIL (0/5) |
| 3 | Deploy VSS in unified mode (one UI where I can search over the generated summari... | PASS (5/5) | FAIL (0/5) |
| 4 | I'm done testing VSS for today. Please stop all the containers and also wipe the... | PASS (5/5) | FAIL (0/5) |
| | **Mean ±σ** | **100% ±0%** | **0% ±0%** |
