<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: text-to-speech-user

**Agent**: GitHub Copilot (Claude Sonnet 5) — single-model self-evaluation
**Grader**: GitHub Copilot (Claude Sonnet 5) — same session, self-graded
**Date**: 2026-10-07
**Evals**: 1–8 (1 reasoned pass per configuration)

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
| w/o skill | 1 / 8 |
| w/ skill | 8 / 8 |
| **Lift** | **+7 ↑** |

### Pass rate (avg ± σ across evals, by expectations met per eval)

| Configuration | Pass rate |
|---|---|
| w/o skill | 38% ±25% |
| w/ skill | 100% ±0% |
| **Lift** | **+62pp ↑** |

## Per-Eval Detail

> Each cell is PASS/FAIL for that reasoned run, with the count of expectations judged met in parentheses (e.g. `PASS (5/5)`).

| Eval | Prompt (abridged) | w/ skill | w/o skill |
|---|---|---|---|
| 1 | Generate a WAV greeting from text and save it to a file. | PASS (5/5) | PASS (5/5) |
| 2 | Migrate an OpenAI-mp3 client to this service with minimal changes. | PASS (5/5) | FAIL (2/5) |
| 3 | `model` field doesn't change which model actually runs — is this a bug? | PASS (5/5) | FAIL (1/5) |
| 4 | Qwen `voice_design` request with `voice` set returns HTTP 400 — fix it. | PASS (5/5) | FAIL (1/5) |
| 5 | Stream longer narration; only one SSE event comes back — is that wrong? | PASS (5/5) | FAIL (2/5) |
| 6 | Punctuation-only input closes the stream with an error event immediately. | PASS (5/5) | FAIL (1/5) |
| 7 | Don't know if SpeechT5 or Qwen is deployed; want to use `instructions`. | PASS (5/5) | FAIL (1/5) |
| 8 | Unknown `voice` name returns 400 instead of falling back to default. | PASS (5/5) | FAIL (2/5) |
| | **Mean ±σ** | **100% ±0%** | **38% ±25%** |

## Why the Lift Is Concentrated in Evals 2–8

Eval 1 is answerable from the service's top-level README/get-started guide
alone, so a baseline agent that skims repository docs performs just as well
with or without the skill. Evals 2–8 each hinge on a specific,
model-dependent validation rule or response-shape detail that is easy to
get wrong without the skill's grounded references — the `response_format`
being limited to `wav`/`json`, the `model` field being accepted but inert,
the sharply different `voice`/`instructions` contracts between SpeechT5,
Qwen `custom_voice`, and Qwen `voice_design`, the single-event streaming
case being expected rather than broken, and unknown voice names failing
closed instead of silently defaulting — exactly the kind of
misconception-correcting detail
[model-and-voice-guide.md](../references/model-and-voice-guide.md) and
[integration-troubleshooting.md](../references/integration-troubleshooting.md)
are designed to surface before the agent guesses.
