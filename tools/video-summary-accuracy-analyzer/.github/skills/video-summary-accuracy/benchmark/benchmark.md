<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: video-summary-accuracy

> **Status: pending.** No benchmark run has been recorded yet. Replace every
> `TBD` below with measured results after running the evals in
> [`../evals/evals.json`](../evals/evals.json) with and without this skill.
> Do not fill in estimated values.

**Agents**: TBD
**Grader**: TBD
**Date**: TBD
**Evals**: 1, 2, 3 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| TBD | TBD / 3 | TBD / 3 | TBD |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Agent (w/) | Agent (w/o) |
|---|---|---|---|
| 1 | Evaluate how accurate the generated video summary in compare.md is against its reference summary and tell me whether it is good enough. | TBD | TBD |
| 2 | Score summary_eval.md for me. Accept it only if contradiction ratio is at most 10% and MENLI is at least 0. The analyzer might not be running. | TBD | TBD |
| 3 | Compare the reference and generated summaries in notes.md. The file has '## Generated' before '## Reference'. Just fix the order and run it. | TBD | TBD |
| | **Mean ±σ** | **TBD** | **TBD** |

## Running the Benchmark

1. Start the analyzer and confirm `GET http://localhost:8101/api/health`
   returns `"status": "Success"`.
2. For each eval, run the prompt in a fresh agent session with the skill
   installed, then again with it removed.
3. Grade each response against that eval's `expectations`; an eval passes only
   when every expectation is met.
4. Record agent and grader model IDs, run date (UTC), totals, and per-eval
   results above.
