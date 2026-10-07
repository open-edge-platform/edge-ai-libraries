<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: audio-analyzer-user

**Agent**: GitHub Copilot (Claude Sonnet 5) — single-model self-evaluation
**Grader**: GitHub Copilot (Claude Sonnet 5) — same session, self-graded
**Date**: 2026-10-07
**Evals**: 1–8 (1 reasoned pass per configuration)

## Methodology Note (Read Before Trusting These Numbers)

This benchmark was **not** produced by the automated multi-agent harness used
for sibling skills in this repository (which dispatches independent
`claude-haiku-4.5`/`claude-sonnet-5` agent runs and grades them with a
separate `gpt-5.3-codex` grader, recording wall-clock time and token counts
per run). That harness executes outside this session and was not available
here.

Instead, each eval below was evaluated by directly reasoning through the
likely answer a capable coding agent would give **with** the
`audio-analyzer-user` skill loaded versus **without** it (general knowledge
of OpenAI-style Whisper APIs plus a quick skim of repository docs, but
without the skill's curated endpoint/troubleshooting references), then
scoring both against the `expectations` list in
[`../evals/evals.json`](../evals/evals.json).

Because no independent agent processes were actually run, **time and token
metrics are not reported** — fabricating those numbers would misrepresent
real measurements. Re-run this skill through the repository's standard
skill-benchmark harness (see sibling skills such as
`model-download-user/.github/skills/.../benchmark/benchmark.md` for the
expected format) to produce an independently measured, reproducible score.

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
| w/o skill | 45% ±24% |
| w/ skill | 100% ±0% |
| **Lift** | **+55pp ↑** |

## Per-Eval Detail

> Each cell is PASS/FAIL for that reasoned run, with the count of expectations judged met in parentheses (e.g. `PASS (5/5)`).

| Eval | Prompt (abridged) | w/ skill | w/o skill |
|---|---|---|---|
| 1 | Transcribe call_042.wav as plain text, no streaming. | PASS (5/5) | PASS (5/5) |
| 2 | Point the OpenAI SDK's streaming client at this self-hosted service. | PASS (5/5) | FAIL (3/5) |
| 3 | stream=true + response_format=srt returns HTTP 400 — why, and fix it. | PASS (5/5) | FAIL (2/5) |
| 4 | Build live mic transcription over the WebSocket; assumes the service captures the mic. | PASS (5/5) | FAIL (2/5) |
| 5 | input_audio_buffer.speech_started never fires for a quiet mic recording. | PASS (5/5) | FAIL (2/5) |
| 6 | Get a per-chunk/session sentiment label alongside the transcript. | PASS (5/5) | FAIL (1/5) |
| 7 | POST /transcriptions response doesn't look like the OpenAI Whisper shape. | PASS (5/5) | FAIL (1/5) |
| 8 | device=GPU form field ignored on the NDJSON streaming endpoint. | PASS (5/5) | FAIL (2/5) |
| | **Mean ±σ** | **100% ±0%** | **45% ±24%** |

## Why the Lift Is Concentrated in Evals 2–8

Eval 1 is answerable from the service's top-level README/get-started guide
alone, so a baseline agent that skims repository docs performs just as well
with or without the skill. Evals 2–8 each hinge on a specific, easy-to-miss
contract detail that is not obvious from a surface read of the docs (the
`stream`/`response_format` restriction, the realtime socket not capturing a
microphone itself, VAD threshold semantics, sentiment being deployment-time
only, the VSS-compatible route having a different response shape, and the
per-endpoint scope of the `device` override) — exactly the kind of
misconception-correcting detail this skill's
[integration-troubleshooting.md](../references/integration-troubleshooting.md)
and [endpoint-reference.md](../references/endpoint-reference.md) references
are designed to surface before the agent guesses.
