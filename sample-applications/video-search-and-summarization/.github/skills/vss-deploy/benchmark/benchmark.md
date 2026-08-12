<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-deploy

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T09:13:29Z  
**Evals**: 1, 2, 3, 4, 5, 90 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 0 / 6 | 2 / 6 | **+2 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 3% ±8% | 70% ±30% | **+67pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 119 s | 191 s | +72 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 164k | 694k | +530k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I just cloned the video-search-and-summarization sample app and want to try vide... | FAIL (4/5) | FAIL (0/5) |
| 2 | Before I commit to anything, I want to see which Docker Compose files and profil... | PASS (5/5) | FAIL (1/5) |
| 3 | VSS is currently running in --summary mode but I actually need to test search in... | FAIL (3/5) | FAIL (0/5) |
| 4 | I'm done testing VSS for today. Please stop all the containers and also wipe the... | FAIL (3/5) | FAIL (0/5) |
| 5 | Deploy VSS in unified mode (one UI where I can search over the generated summari... | PASS (5/5) | FAIL (0/5) |
| 90 | Deploy VSS in summary mode using the defaults, then once it's healthy tell me th... | FAIL (1/5) | FAIL (0/5) |
| | **Mean ±σ** | **70% ±30%** | **3% ±8%** |