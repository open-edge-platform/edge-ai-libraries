<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Benchmark — vss-troubleshoot

_Generated: 2026-07-20T16:31:55+05:30_

## Models

| Role | Model |
|---|---|
| Eval execution (with & without skill) | `claude-sonnet-5` |
| Orchestrator / grader | `claude-opus-4.8` |

**Token source:** Real runtime usage from the local session store (assistant_usage_events), summed per serialized top-level background agent (model claude-sonnet-5) - authoritative token metadata, not an estimate.

## Results summary

| Mode | Evals passed | Expectations passed | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| **With skill** | 6/7 | 28/30 | 484820 | 12820 | 497640 |
| **Without skill** | 0/7 | 5/30 | 224113 | 8586 | 232699 |

**Skill impact:** +6 evals passed with the skill vs without.

## Per-eval detail

| Eval | Prompt file | With skill | Without skill |
|---|---|---|---|
| 1 | `example-prompts/01-is-vss-up.md` | PASS (4/4) | FAIL (0/4) |
| 2 | `example-prompts/02-ovms-crash-loop.md` | PASS (4/4) | FAIL (1/4) |
| 3 | `example-prompts/03-no-summary-appears.md` | PASS (5/5) | FAIL (1/5) |
| 4 | `example-prompts/04-search-returns-nothing.md` | PASS (4/4) | FAIL (2/4) |
| 5 | `example-prompts/05-port-conflict.md` | PASS (4/4) | FAIL (1/4) |
| 6 | `example-prompts/06-rabbitmq-minio-ingestion-stall.md` | PASS (4/4) | FAIL (0/4) |
| 90 | `example-prompts/07-bootstrap-fresh-machine.md` | FAIL (3/5) | FAIL (0/5) |

## Token consumption

- **With skill:** 497640 total tokens (484820 in / 12820 out)
- **Without skill:** 232699 total tokens (224113 in / 8586 out)

## Eval 90 re-run (implicit bootstrap detection)

_Re-generated: 2026-07-21T03:00:48Z_

Eval 90 was rewritten to test IMPLICIT bootstrap behavior (no explicit 'fresh machine'/clone wording in the prompt) and re-run in isolation. The mode_tokens block above still reflects the ORIGINAL full-suite run (unchanged, not corrupted by this partial re-run); these numbers are for the eval-90-only re-run.

- Prompt file: `example-prompts/07-bootstrap-fresh-machine.md`
- With skill: FAIL (3/5)
- Without skill: FAIL (0/5)

| Mode | Input tokens | Output tokens | Total tokens |
|---|---|---|---|
| With skill (eval 90 only) | 316265 | 4381 | 320646 |
| Without skill (eval 90 only) | 274099 | 3262 | 277361 |

**Token source:** top-level background agent usage window (partially shared-pool batched for 13/15 skills; see grader_note)

