# Skill Benchmark: vlm-model-selector

**Agent**: Copilot (`Claude Haiku 4.5`)  
**Grader**: Copilot (`Claude Sonnet 5`, inline)
**Date**: 2026-11-28T08:29:51Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 (1 run per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 49% ± 31% | +0.51 |
| Time | 0.0s ± 0.0s | 0.0s ± 0.0s | +0.0s |
| Tokens | 0 ± 0 | 0 ± 0 | +0 |

Time/Tokens are not reported: grading was done inline against saved response
text rather than via the Task-notification telemetry skill-creator normally
captures, so no real duration/token data was collected for this run.

## Per-Eval Detail

| Eval | Name | With skill | Without skill |
|---|---|---|---|
| 1 | forklift-safety-decomposition | PASS (4/4) | FAIL (1/4) |
| 2 | sparse-prompt-forces-elicitation | PASS (3/3) | FAIL (0/3) |
| 3 | audio-modality-widens-search | PASS (3/3) | FAIL (2/3) |
| 4 | license-gate-excludes-noncommercial-candidate | PASS (3/3) | PASS (3/3) |
| 5 | bias-self-check-on-family-skewed-shortlist | PASS (3/3) | FAIL (1/3) |
| 6 | single-model-check-verifies-currency-and-license | PASS (4/4) | FAIL (1/4) |
| 7 | gated-candidate-never-requests-secret-value | PASS (3/3) | FAIL (1/3) |
| 8 | pure-counting-task-redirected-away-from-vlm | PASS (3/3) | FAIL (1/3) |
| 9 | video-modality-requires-dedicated-benchmark-check | PASS (3/3) | FAIL (2/3) |
| 10 | stale-generation-naming-trap | PASS (3/3) | PASS (3/3) |
| 11 | gemma-license-overconfidence-trap | PASS (3/3) | FAIL (2/3) |
| 12 | single-pick-request-still-shows-diligence | PASS (3/3) | FAIL (1/3) |
| | **Eval-level full-pass rate** | **12/12 (100%)** | **2/12 (17%)** |

## Analyst Notes

- **Non-discriminating evals in this run:** #4 and #10 passed fully even
  without the skill. For #4, the license text was handed to the model
  directly in the prompt, and a capable small model applies an explicit
  non-commercial clause correctly without needing the skill's taxonomy —
  consistent with this eval's own `differentiator_rationale` ("weak-medium
  differentiator"). For #10, the test harness told *both* conditions
  "assume you cannot reach the internet," which likely primed appropriate
  hedging regardless of skill guidance — a flaw in this eval's test design,
  not a finding about the skill. A future iteration should drop that
  internet-access caveat from the baseline prompt (or add a separate variant
  that doesn't warn the model at all) to get a cleaner read on whether the
  model would have fabricated a checkpoint name unprompted.
- **Where the predicted strong/medium differentiators actually showed the
  largest gaps:** #1, #2, #6, #7, #8, #12 — all evals pre-labeled as
  "strong" or safety-critical differentiators in `evals/evals.json` — had
  the lowest without-skill scores (0.0–0.33). This is a good sign that the
  differentiator_rationale written before running anything was a reasonably
  accurate prediction, not just plausible-sounding theory.
- **Partial-credit cases worth a second look:** #3, #9, and #11 all landed
  at 2/3 without the skill — the baseline model is generically well-aligned
  enough to catch roughly two-thirds of what's being checked (audio-gap
  recognition, naming a video benchmark, declining to give a confident
  verdict) but consistently missed the more specific, skill-encoded piece
  (consequential-decision/human-in-the-loop framing, distinguishing
  accuracy-signal confidence tiers, and the cross-generation license-change
  caveat, respectively). This matches the thesis that a skill's value is
  concentrated in the specific, hard-to-derive-from-first-principles details
  rather than the general shape of the answer.
- **Assertion possibly too easy to satisfy vacuously:** eval 12's third
  assertion ("if genuinely skipping elicitation, states the assumptions
  explicitly") passed for the with-skill run only because the run didn't
  skip elicitation at all (vacuous pass). Consider rewriting this as two
  separate assertions — one for "asks before committing" and a second,
  independent one for "if it ever does skip, does it disclose assumptions" —
  so a future run that *does* skip can't accidentally get credit it didn't
  earn.