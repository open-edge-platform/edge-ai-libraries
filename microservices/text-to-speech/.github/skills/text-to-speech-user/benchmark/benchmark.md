<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: text-to-speech-user

**Agents**: GitHub Copilot (Claude Sonnet 5) — single-model self-evaluation
**Grader**: GitHub Copilot (Claude Sonnet 5) — same session, self-graded
**Date**: 2026-10-09
**Evals**: 1–13 (1 reasoned pass per configuration)

## Methodology Note (Read Before Trusting These Numbers)

This benchmark was **not** produced by the automated multi-agent harness used
for sibling skills in this repository (which dispatches independent agent
runs — e.g. `claude-haiku-4.5`/`claude-sonnet-5` — and grades them with a
separate `gpt-5.3-codex` grader, recording wall-clock time and token counts
per run). That harness executes outside this session and was not available
here.

Instead, each eval below was evaluated by directly reasoning through the
likely answer a capable coding agent would give **with** the
`text-to-speech-user` skill loaded versus **without** it (general knowledge
of OpenAI-style speech APIs plus a quick skim of repository docs, but
without the skill's curated per-model validation rules and troubleshooting
references), then scoring both against the `expectations` list in
[`../evals/evals.json`](../evals/evals.json).

Because no independent agent processes were actually run, **time and token
metrics are not reported** — fabricating those numbers would misrepresent
real measurements. Re-run this skill through the repository's standard
skill-benchmark harness (see sibling skills such as
`model-download/.github/skills/model-download-user/benchmark/benchmark.md`
for the expected format) to produce an independently measured, reproducible
score.

## Summary

### Evals passed

| Configuration | Evals passed |
|---|---|
| w/o skill | 1 / 13 |
| w/ skill | 13 / 13 |
| **Lift** | **+12 ↑** |

### Pass rate (avg ± σ across evals, by expectations met per eval)

| Configuration | Pass rate |
|---|---|
| w/o skill | 31% ±22% |
| w/ skill | 100% ±0% |
| **Lift** | **+69pp ↑** |

## Per-Eval Detail

> Each cell is PASS/FAIL for that reasoned run, with the count of expectations judged met in parentheses (e.g. `PASS (5/5)`).

| Eval | Prompt (abridged) | w/ skill | w/o skill |
|---|---|---|---|
| 1 | Generate a WAV greeting from text and save it to a file. | PASS (5/5) | PASS (5/5) |
| 2 | Migrate an OpenAI-mp3 client to this service with minimal changes. | PASS (5/5) | FAIL (2/5) |
| 3 | `model` field doesn't change which model actually runs — is this a bug? | PASS (5/5) | FAIL (1/5) |
| 4 | Qwen3-TTS/voice_design deployment never responds to /health at all — client bug or deployment issue? | PASS (5/5) | FAIL (1/5) |
| 5 | Stream longer narration; only one SSE event comes back — is that wrong? | PASS (5/5) | FAIL (2/5) |
| 6 | Punctuation-only input closes the stream with an error event immediately. | PASS (5/5) | FAIL (1/5) |
| 7 | Don't know if SpeechT5 or Qwen is deployed; want to use `instructions`. | PASS (5/5) | FAIL (1/5) |
| 8 | Unknown `voice` name returns 400 instead of falling back to default. | PASS (5/5) | FAIL (2/5) |
| 9 | `device: NPU` rejected instead of gracefully degrading to CPU. | PASS (5/5) | FAIL (1/5) |
| 10 | `GET /v1/audio/voices` field names don't match expected `speakers`/`languages`. | PASS (5/5) | FAIL (1/5) |
| 11 | Kokoro returns audio in a substitute voice instead of the expected 400 for an unsupported name. | PASS (5/5) | FAIL (1/5) |
| 12 | 6000-char input returns 422, not the documented 400 — client bug or doc error? | PASS (5/5) | FAIL (1/5) |
| 13 | persist_outputs=true but storage/<session_id>/ stays empty for streaming requests. | PASS (5/5) | FAIL (1/5) |
| | **Mean ±σ** | **100% ±0%** | **31% ±22%** |

## Why the Lift Is Concentrated in Evals 2–13

Eval 1 is answerable from the service's top-level README/get-started guide
alone, so a baseline agent that skims repository docs performs just as well
with or without the skill. Evals 2–13 each hinge on a specific,
model-dependent validation rule or response-shape detail that is easy to
get wrong without the skill's grounded references — the `response_format`
being limited to `wav`/`json`, the `model` field being accepted but inert,
Qwen3-TTS currently failing at **service startup** rather than per-request
(a recent documentation correction this skill was updated to reflect), the
single-event streaming case being expected rather than broken, an unknown
`voice` name's **model-dependent** outcome (SpeechT5 fails closed with HTTP
400, Kokoro silently falls back to its default voice instead — a second
recent correction), the per-request `device` override being rejected
rather than gracefully downgraded, the current `GET /v1/audio/voices`
response field names, the **422 vs. 400** split between Pydantic schema
validation and service-level validation (a third recent correction), and
`pipeline.persist_outputs` applying only to the non-streaming endpoint (a
fourth recent correction — `Pipeline.synthesize_stream()` never writes to
storage) — exactly the kind of misconception-correcting detail
[model-and-voice-guide.md](../references/model-and-voice-guide.md) and
[integration-troubleshooting.md](../references/integration-troubleshooting.md)
are designed to surface before the agent guesses.
