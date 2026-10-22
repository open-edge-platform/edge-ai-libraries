<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: audio-analyzer-user

**Agents**: Copilot (`claude-sonnet-5.5`)  
**Grader**: Copilot (`claude-sonnet-5.5`)  
**Date**: 2026-10-21T10:19:58Z  
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 3 / 8 | 8 / 8 | **+5 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 85% ±14% | 100% ±0% | **+15pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 270 s | 201 s | -69 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 0 | 0 | +0 ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I have a recorded customer call saved as call_042.wav and I just want the full t... | PASS (5/5) | PASS (5/5) |
| 2 | I already use the official OpenAI Python SDK in my app for Whisper streaming tra... | PASS (5/5) | FAIL (4/5) |
| 3 | My client uploads a subtitle file request with response_format=srt and stream=tr... | PASS (5/5) | FAIL (4/5) |
| 4 | I want to build a live microphone transcription feature in my desktop app using ... | PASS (5/5) | PASS (5/5) |
| 5 | I'm streaming audio to /v1/realtime from a quiet lapel mic recording and input_a... | PASS (5/5) | FAIL (3/5) |
| 6 | I want every uploaded chunk of a long file to produce a sentiment label so I can... | PASS (5/5) | FAIL (4/5) |
| 7 | I set device=GPU as a form field when calling the NDJSON streaming endpoint /v1/... | PASS (5/5) | FAIL (4/5) |
| 8 | My reconnect logic opens WS /v1/realtime?intent=transcription&session_id=../../e... | PASS (5/5) | PASS (5/5) |
| | **Mean ±σ** | **100% ±0%** | **85% ±14%** |