# Skill Benchmark: chatqna-run-unit-tests

**Model**: unspecified (codex CLI default)
**Date**: 2026-08-03T09:02:12Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 (1 run(s) each per configuration)

## Summary

> **How to read this table** — **Avg** is the mean score across all evals; **Std Dev** (the ± spread) measures how much individual evals varied around that average — small spread means the agent behaved consistently, large spread means results were erratic; **Skill Lift** is the gain from loading the skill (with − without).

| Metric | Avg ± Std Dev (With Skill) | Avg ± Std Dev (Without Skill) | Skill Lift (Δ) |
|--------|---------------------------|-------------------------------|----------------|
| Pass Rate (% correct) | 65% avg, ±28% spread (variable) | 30% avg, ±32% spread (unreliable) | +35pp |
| Time (s / question) | 13.4s avg, ±2.5s spread (variable) | 15.5s avg, ±4.5s spread (variable) | -2.1s |
| Tokens (context cost) | 15k avg, ±93 spread (consistent) | 22k avg, ±14k spread (unreliable) | -7k |