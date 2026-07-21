<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmark — vss-add-nest-module

_Generated: 2026-07-20T16:36:55+05:30_

## Models

| Role | Model |
|---|---|
| Eval execution (with & without skill) | `claude-sonnet-5` |
| Orchestrator / grader | `claude-opus-4.8` |

**Token source:** Real runtime usage from the local session store (assistant_usage_events), summed per serialized top-level background agent (model claude-sonnet-5) - authoritative token metadata, not an estimate.

## Results summary

| Mode | Evals passed | Expectations passed | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| **With skill** | 6/7 | 33/35 | 328327 | 12820 | 341147 |
| **Without skill** | 1/7 | 20/35 | 189074 | 9335 | 198409 |

**Skill impact:** +5 evals passed with the skill vs without.

## Per-eval detail

| Eval | Prompt file | With skill | Without skill |
|---|---|---|---|
| 1 | `example-prompts/01-scaffold-basic-module.md` | PASS (5/5) | FAIL (2/5) |
| 2 | `example-prompts/02-add-endpoint-existing-style.md` | PASS (5/5) | FAIL (2/5) |
| 3 | `example-prompts/03-typeorm-persisted-module.md` | PASS (5/5) | FAIL (4/5) |
| 4 | `example-prompts/04-queue-background-processor.md` | PASS (5/5) | FAIL (3/5) |
| 5 | `example-prompts/05-socket-and-events-module.md` | PASS (5/5) | FAIL (4/5) |
| 6 | `example-prompts/06-full-feature-with-dependencies.md` | PASS (5/5) | PASS (5/5) |
| 90 | `example-prompts/07-bootstrap-fresh-machine.md` | FAIL (3/5) | FAIL (0/5) |

## Token consumption

- **With skill:** 341147 total tokens (328327 in / 12820 out)
- **Without skill:** 198409 total tokens (189074 in / 9335 out)

## Eval 90 re-run (implicit bootstrap detection)

_Re-generated: 2026-07-21T03:00:47Z_

Eval 90 was rewritten to test IMPLICIT bootstrap behavior (no explicit 'fresh machine'/clone wording in the prompt) and re-run in isolation. The mode_tokens block above still reflects the ORIGINAL full-suite run (unchanged, not corrupted by this partial re-run); these numbers are for the eval-90-only re-run.

- Prompt file: `example-prompts/07-bootstrap-fresh-machine.md`
- With skill: FAIL (3/5)
- Without skill: FAIL (0/5)

| Mode | Input tokens | Output tokens | Total tokens |
|---|---|---|---|
| With skill (eval 90 only) | 642918 | 5562 | 648480 |
| Without skill (eval 90 only) | 526636 | 4158 | 530794 |

**Token source:** top-level background agent usage window (partially shared-pool batched for 13/15 skills; see grader_note)

