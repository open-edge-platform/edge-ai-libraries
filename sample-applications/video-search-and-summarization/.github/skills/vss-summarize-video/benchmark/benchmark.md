<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-summarize-video

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
| Copilot (`claude-sonnet-5`) | 15% ±10% | 100% ±0% | **+85pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 129 s | 173 s | +44 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5`) | 190k | 989k | +799k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I just uploaded a video called "loading-dock-cam.mp4" to VSS. Can you summarize ... | PASS (5/5) | FAIL (1/5) |
| 2 | I have a 40-minute warehouse security video already ingested with videoId `vid-7... | PASS (5/5) | FAIL (1/5) |
| 3 | For videoId `parking-lot-042`, I don't want a single blended summary - I want to... | PASS (5/5) | FAIL (1/5) |
| 4 | I only have this skills folder on my machine - the VSS application source isn't ... | PASS (5/5) | FAIL (0/5) |
| | **Mean ±σ** | **100% ±0%** | **15% ±10%** |
