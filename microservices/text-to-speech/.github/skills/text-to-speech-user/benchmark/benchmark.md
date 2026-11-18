<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: text-to-speech-user

**Agents**: Copilot (`claude-sonnet-5.5`)  
**Grader**: Copilot (`claude-sonnet-5.5`)  
**Date**: 2026-10-21T10:06:38Z  
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 6 / 13 | 10 / 13 | **+4 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 85% ±19% | 95% ±9% | **+11pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 402 s | 390 s | -12 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 0 | 0 | +0 ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I want to generate a WAV greeting for my kiosk app from the text 'Welcome, pleas... | PASS (5/5) | FAIL (4/5) |
| 2 | My app currently calls OpenAI's real text-to-speech API and requests response_fo... | FAIL (4/5) | FAIL (4/5) |
| 3 | I'm sending {"model": "tts-1-hd", "input": "Hello"} expecting this service to lo... | PASS (5/5) | FAIL (4/5) |
| 4 | My team told me our text-to-speech deployment uses Qwen3-TTS with voice_design, ... | PASS (5/5) | FAIL (2/5) |
| 5 | I want to stream longer narration text so playback can start before the whole th... | PASS (5/5) | PASS (5/5) |
| 6 | A streaming request for a string that's just a bunch of punctuation marks (somet... | PASS (5/5) | PASS (5/5) |
| 7 | I don't know whether the currently running deployment is SpeechT5 or Qwen, and I... | PASS (5/5) | PASS (5/5) |
| 8 | I requested voice: 'Morgan' against a SpeechT5 deployment and got a 400 error in... | PASS (5/5) | PASS (5/5) |
| 9 | I set "device": "NPU" in my request to POST /v1/audio/speech, expecting it to ju... | FAIL (4/5) | PASS (5/5) |
| 10 | I called GET /v1/audio/voices expecting fields named speakers and languages like... | PASS (5/5) | FAIL (3/5) |
| 11 | I requested voice: 'Morgan' against the default Kokoro deployment, expected an H... | PASS (5/5) | FAIL (4/5) |
| 12 | My client sends a 6000-character input string to POST /v1/audio/speech expecting... | FAIL (4/5) | PASS (5/5) |
| 13 | The deployment has pipeline.persist_outputs set to true. I'm using POST /v1/audi... | PASS (5/5) | FAIL (4/5) |
| | **Mean ±σ** | **95% ±9%** | **85% ±19%** |