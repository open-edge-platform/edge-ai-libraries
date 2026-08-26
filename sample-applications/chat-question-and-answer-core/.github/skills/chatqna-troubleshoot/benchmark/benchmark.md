# Skill Benchmark: chatqna-troubleshoot

**Model**: gpt-5.6-terra (codex CLI default)
**Date**: 2026-08-03T08:13:39Z
**Evals**: 1, 2, 3 (1 run(s) each per configuration)

## Summary

> **How to read this table** — **Avg** is the mean score across all evals; **Std Dev** (the ± spread) measures how much individual evals varied around that average — small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with − without).

| Metric | Avg ± Std Dev (With Skill) | Avg ± Std Dev (Without Skill) | Skill Lift (Δ) |
|--------|---------------------------|-------------------------------|----------------|
| Pass Rate (% correct) | 100% avg, ±0% spread (consistent) | 53% avg, ±12% spread (variable) | +47pp |
| Time (s / question) | 37.9s avg, ±3.0s spread (consistent) | 46.0s avg, ±12.7s spread (variable) | -8.1s |
| Tokens (context cost) | 18k avg, ±221 spread (consistent) | 16k avg, ±709 spread (consistent) | +2k |
