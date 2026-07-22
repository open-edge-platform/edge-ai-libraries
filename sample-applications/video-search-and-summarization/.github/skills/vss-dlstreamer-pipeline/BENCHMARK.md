<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmark — vss-dlstreamer-pipeline

_Generated: 2026-07-20T17:02:46+05:30_

## Models

| Role | Model |
|---|---|
| Eval execution (with & without skill) | `claude-sonnet-5` |
| Orchestrator / grader | `claude-opus-4.8` |

**Token source:** Real runtime usage from the local session store (assistant_usage_events), summed per serialized top-level background agent (model claude-sonnet-5) - authoritative token metadata, not an estimate.

## Results summary

| Mode | Evals passed | Expectations passed | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| **With skill** | 6/7 | 34/35 | 329983 | 14378 | 344361 |
| **Without skill** | 0/7 | 12/35 | 632638 | 24789 | 657427 |

**Skill impact:** +6 evals passed with the skill vs without.

## Per-eval detail

| Eval | Prompt file | With skill | Without skill |
|---|---|---|---|
| 1 | `example-prompts/01-tune-frame-extraction-rate.md` | PASS (5/5) | FAIL (3/5) |
| 2 | `example-prompts/02-add-detection-model.md` | PASS (5/5) | FAIL (1/5) |
| 3 | `example-prompts/03-debug-broken-pipeline-string.md` | PASS (5/5) | FAIL (2/5) |
| 4 | `example-prompts/04-add-new-pipeline-name.md` | PASS (5/5) | FAIL (2/5) |
| 5 | `example-prompts/05-explain-request-payload.md` | PASS (5/5) | FAIL (2/5) |
| 6 | `example-prompts/06-validate-publish-pipeline-change.md` | PASS (5/5) | FAIL (2/5) |
| 90 | `example-prompts/07-bootstrap-fresh-machine.md` | FAIL (4/5) | FAIL (0/5) |

## Token consumption

- **With skill:** 344361 total tokens (329983 in / 14378 out)
- **Without skill:** 657427 total tokens (632638 in / 24789 out)

## Eval 90 re-run (implicit bootstrap detection)

_Re-generated: 2026-07-21T03:00:47Z_

Eval 90 was rewritten to test IMPLICIT bootstrap behavior (no explicit 'fresh machine'/clone wording in the prompt) and re-run in isolation. The mode_tokens block above still reflects the ORIGINAL full-suite run (unchanged, not corrupted by this partial re-run); these numbers are for the eval-90-only re-run.

- Prompt file: `example-prompts/07-bootstrap-fresh-machine.md`
- With skill: FAIL (4/5)
- Without skill: FAIL (0/5)

| Mode | Input tokens | Output tokens | Total tokens |
|---|---|---|---|
| With skill (eval 90 only) | 316265 | 4381 | 320646 |
| Without skill (eval 90 only) | 274099 | 3262 | 277361 |

**Token source:** top-level background agent usage window (partially shared-pool batched for 13/15 skills; see grader_note)

