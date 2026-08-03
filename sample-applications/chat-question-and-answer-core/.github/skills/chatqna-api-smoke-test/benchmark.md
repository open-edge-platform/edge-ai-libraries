# Skill Benchmark: chatqna-api-smoke-test

**Model**: gpt-5.6-terra (codex CLI default)
**Date**: 2026-08-03T08:18:19Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 (1 run(s) each per configuration)

## Summary

> **How to read this table** — **Avg** is the mean score across all evals; **Std Dev** (the ± spread) measures how much individual evals varied around that average — small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with − without).

| Metric | Avg ± Std Dev (With Skill) | Avg ± Std Dev (Without Skill) | Skill Lift (Δ) |
|--------|---------------------------|-------------------------------|----------------|
| Pass Rate (% correct) | 82% avg, ±32% spread (variable) | 37% avg, ±28% spread (unreliable) | +45pp |
| Time (s / question) | 17.3s avg, ±2.3s spread (consistent) | 20.1s avg, ±6.0s spread (variable) | -2.8s |
| Tokens (context cost) | 16k avg, ±128 spread (consistent) | 19k avg, ±10k spread (unreliable) | -3k |
