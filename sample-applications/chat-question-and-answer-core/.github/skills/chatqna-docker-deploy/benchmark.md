# Skill Benchmark: chatqna-docker-deploy

**Model**: gpt-5.6-terra (codex CLI default)
**Date**: 2026-08-03T08:48:53Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 (1 run(s) each per configuration)

## Summary

> **How to read this table** — **Avg** is the mean score across all evals; **Std Dev** (the ± spread) measures how much individual evals varied around that average — small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with − without).

| Metric | Avg ± Std Dev (With Skill) | Avg ± Std Dev (Without Skill) | Skill Lift (Δ) |
|--------|---------------------------|-------------------------------|----------------|
| Pass Rate (% correct) | 83% avg, ±23% spread (variable) | 23% avg, ±32% spread (unreliable) | +60pp |
| Time (s / question) | 14.4s avg, ±4.0s spread (variable) | 20.6s avg, ±6.5s spread (variable) | -6.2s |
| Tokens (context cost) | 16k avg, ±202 spread (consistent) | 17k avg, ±8k spread (variable) | -652 |
