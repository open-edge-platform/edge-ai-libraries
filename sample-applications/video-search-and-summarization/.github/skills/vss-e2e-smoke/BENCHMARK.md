<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmark — vss-e2e-smoke

_Generated: 2026-07-20T17:07:56+05:30_

## Models

| Role | Model |
|---|---|
| Eval execution (with & without skill) | `claude-sonnet-5` |
| Orchestrator / grader | `claude-opus-4.8` |

**Token source:** Real runtime usage from the local session store (assistant_usage_events), summed per serialized top-level background agent (model claude-sonnet-5) - authoritative token metadata, not an estimate.

## Results summary

| Mode | Evals passed | Expectations passed | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| **With skill** | 6/7 | 34/35 | 447803 | 11706 | 459509 |
| **Without skill** | 0/7 | 10/35 | 224974 | 10402 | 235376 |

**Skill impact:** +6 evals passed with the skill vs without.

## Per-eval detail

| Eval | Prompt file | With skill | Without skill |
|---|---|---|---|
| 1 | `example-prompts/01-fresh-summary-verify.md` | PASS (5/5) | FAIL (2/5) |
| 2 | `example-prompts/02-search-mode-custom-port.md` | PASS (5/5) | FAIL (0/5) |
| 3 | `example-prompts/03-dual-mode-full-coverage.md` | PASS (5/5) | FAIL (2/5) |
| 4 | `example-prompts/04-unified-mode-sanity.md` | PASS (5/5) | FAIL (2/5) |
| 5 | `example-prompts/05-diagnose-summary-fail.md` | PASS (5/5) | FAIL (2/5) |
| 6 | `example-prompts/06-bootstrap-fresh-machine.md` | PASS (5/5) | FAIL (2/5) |
| 90 | `example-prompts/07-bootstrap-fresh-machine.md` | FAIL (4/5) | FAIL (0/5) |

## Token consumption

- **With skill:** 459509 total tokens (447803 in / 11706 out)
- **Without skill:** 235376 total tokens (224974 in / 10402 out)

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

