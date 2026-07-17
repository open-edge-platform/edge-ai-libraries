# Skill Benchmark: model-download-user

**Model**: copilot=claude-sonnet-5, claude=claude-sonnet-4-6, codex=unspecified (codex CLI default)
**Date**: 2026-07-15T04:41:26Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 run(s) each per configuration)

## Summary

> **How to read this table** — **Avg** is the mean score across all evals; **Std Dev** (the ± spread) measures how much individual evals varied around that average — small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with − without).

| Metric | Config | Copilot (Avg ± Std Dev) | Claude (Avg ± Std Dev) | Codex (Avg ± Std Dev) |
|--------|--------|---|---|---|
| Pass Rate (% correct) | with_skill | 92% avg, ±15% spread (variable) | 92% avg, ±10% spread (consistent) | 95% avg, ±9% spread (consistent) |
|  | without_skill | 60% avg, ±40% spread (unreliable) | 75% avg, ±35% spread (variable) | 88% avg, ±15% spread (variable) |
| Time (s / question) | with_skill | 25.8s avg, ±2.1s spread (consistent) | 27.2s avg, ±5.6s spread (variable) | 30.6s avg, ±4.8s spread (variable) |
|  | without_skill | 27.4s avg, ±4.1s spread (variable) | 21.8s avg, ±3.2s spread (consistent) | 28.3s avg, ±7.4s spread (variable) |
| Tokens (context cost) | with_skill | 86k avg, ±10k spread (consistent) | 66k avg, ±10k spread (consistent) | 64k avg, ±18k spread (variable) |
|  | without_skill | 61k avg, ±30k spread (variable) | 53k avg, ±22k spread (variable) | 50k avg, ±17k spread (variable) |

## Notes

- Cross-CLI comparison of ['with_skill', 'without_skill'] across: copilot, claude, codex.
- Each CLI ran the identical eval prompts against the identical skill, using each CLI's own non-interactive/headless mode. run_summary is keyed run_summary[config][cli] — each config (with_skill/without_skill) shows the stats for that CLI under that configuration.
- Model per CLI: copilot=claude-sonnet-5, claude=claude-sonnet-4-6, codex=unspecified (codex CLI default). Copilot and Claude report the actual model used per-run (see each run's timing.json); Codex's non-interactive JSON output does not expose which model served the request, so its value reflects what was explicitly requested via --codex-model, or 'unspecified' if the CLI's own built-in default was used.