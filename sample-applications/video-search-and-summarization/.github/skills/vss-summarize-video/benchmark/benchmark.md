<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-summarize-video

**Agents**: Copilot (`claude-sonnet-5`)
**Grader**: Copilot (`claude-sonnet-5`)
**Date**: 2026-08-22T20:28:07Z
**Evals**: 1, 2, 3, 4 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 1 / 4 | 4 / 4 | **+3 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 25% ±50% | 100% ±0% | **+75pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 418 s | 151 s | -267 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 1205k | 658k | -547k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Claude (w/) | Claude (w/o) |
|---|---|---|---|
| 1 | I uploaded a clip called `loading-dock-cam.mp4` to VSS and I just want the gist ... | PASS (5/5) | FAIL (0/5) |
| 2 | I have a 40-minute warehouse security video already ingested with videoId `vid-7... | PASS (5/5) | FAIL (0/5) |
| 3 | For videoId `parking-lot-042` I don't want one blended summary - I want each chu... | PASS (5/5) | PASS (5/5) |
| 4 | I'm on a fresh machine - the VSS application source isn't checked out anywhere a... | PASS (5/5) | FAIL (0/5) |
| | **Mean ±σ** | **100% ±0%** | **25% ±50%** |
