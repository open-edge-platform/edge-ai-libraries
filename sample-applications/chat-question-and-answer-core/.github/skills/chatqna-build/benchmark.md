# Skill Benchmark: chatqna-build

**Model**: gpt-5.6-terra (codex CLI default)
**Date**: 2026-08-03T08:23:45Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 (1 run(s) each per configuration)

## Summary

> **How to read this table** — **Avg** is the mean score across all evals; **Std Dev** (the ± spread) measures how much individual evals varied around that average — small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with − without).

| Metric | Avg ± Std Dev (With Skill) | Avg ± Std Dev (Without Skill) | Skill Lift (Δ) |
|--------|---------------------------|-------------------------------|----------------|
| Pass Rate (% correct) | 95% avg, ±11% spread (consistent) | 26% avg, ±36% spread (unreliable) | +69pp |
| Time (s / question) | 13.8s avg, ±2.9s spread (variable) | 19.3s avg, ±8.1s spread (variable) | -5.5s |
| Tokens (context cost) | 15k avg, ±132 spread (consistent) | 20k avg, ±11k spread (unreliable) | -5k |
