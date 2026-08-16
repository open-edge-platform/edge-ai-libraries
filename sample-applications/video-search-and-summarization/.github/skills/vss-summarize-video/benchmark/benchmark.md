<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: vss-summarize-video

**Agents**: Copilot (`claude-haiku-4.5`)  
**Grader**: Copilot (`gpt-5.3-codex`)  
**Date**: 2026-08-07T09:25:19Z  
**Evals**: 1, 2, 3, 4, 5, 6, 90 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 0 / 7 | 2 / 7 | **+2 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 6% ±10% | 51% ±36% | **+46pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 142 s | 225 s | +83 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-haiku-4.5`) | 191k | 931k | +740k ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I just uploaded a video called "loading-dock-cam.mp4" to VSS. Can you summarize ... | FAIL (2/5) | FAIL (0/5) |
| 2 | I have a 40-minute warehouse security video already ingested with videoId `vid-7... | PASS (5/5) | FAIL (1/5) |
| 3 | Summarize the interview clip with videoId `int-2024-05`, and please include an a... | FAIL (2/5) | FAIL (0/5) |
| 4 | For videoId `parking-lot-042`, I don't want a single blended summary - I want to... | PASS (5/5) | FAIL (1/5) |
| 5 | Can you list all the summary pipelines currently stored in VSS, and then delete ... | FAIL (0/5) | FAIL (0/5) |
| 6 | I only have this skills folder on my machine - the VSS application source isn't ... | FAIL (2/5) | FAIL (0/5) |
| 90 | I just finished ingesting a video called "loading-bay-cam-03.mp4" into VSS and i... | FAIL (2/5) | FAIL (0/5) |
| | **Mean ±σ** | **51% ±36%** | **6% ±10%** |