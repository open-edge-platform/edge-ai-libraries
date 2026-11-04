<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Skill Benchmark: agent-harness-install

**Agents**: Copilot (`claude-sonnet-5.5`)  
**Grader**: Copilot (`claude-sonnet-5.5`)  
**Date**: 2026-11-04T07:39:20Z  
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 run per configuration)

## Summary

> Skill lift = with skill − without skill. ↑ = better, ↓ = higher cost (expected).

### Evals passed

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 3 / 8 | 6 / 8 | **+3 ↑** |

### Pass rate (avg ± σ across evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 49% ±44% | 84% ±35% | **+36pp ↑** |

### Time (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 254 s | 247 s | -8 s ↓ |

### Tokens (total across all evals)

| Agent | w/o skill | w/ skill | Lift |
|---|---|---|---|
| Copilot (`claude-sonnet-5.5`) | 0 | 0 | +0 ↓ |

## Per-Eval Detail

> Each cell is PASS/FAIL for that run, with the count of expectations met in parentheses (e.g. `PASS (5/5)`); `n/a` means no grading.json was found for that (eval, config, agent) combination.

| Eval | Prompt | Copilot (w/) | Copilot (w/o) |
|---|---|---|---|
| 1 | I have an Intel Core Ultra laptop running Ubuntu 24.04. Install OpenClaw for me ... | PASS (5/5) | FAIL (2/5) |
| 2 | We already run vLLM at http://10.0.0.5:8000/v1 behind an API key. I want Hermes ... | PASS (5/5) | FAIL (0/5) |
| 3 | Install deepagents-code and pull the model with the ollama hub: qwen2.5:7b. Will... | FAIL (3/4) | FAIL (0/4) |
| 4 | ./install.sh dies on our Linux server with 'syntax error near unexpected token'.... | PASS (3/3) | PASS (3/3) |
| 5 | dcode installed fine but when I run it I get MissingCredentialsError, and on the... | PASS (4/4) | FAIL (1/4) |
| 6 | Remove everything agent-harness-install put on this machine for OpenClaw, but ke... | PASS (4/4) | FAIL (1/4) |
| 7 | Install the Intel GPU kernel driver and the Level-Zero and OpenCL compute runtim... | PASS (2/2) | PASS (2/2) |
| 8 | How do I write a custom tool for an OpenClaw agent that calls my REST API? | FAIL (0/2) | PASS (2/2) |
| | **Mean ±σ** | **84% ±35%** | **49% ±44%** |

## Run notes

- Single run per configuration, Copilot CLI only. Claude Code and Codex were not run. Treat the numbers as one sample: repeat runs of the same suite, including after small rewording of evals, scored between 84% and 91% with the skill and between 45% and 54% without it.
- The host was Windows, so the agent did not execute the installer. Responses are graded on the commands and guidance they gave.
- The runner prepends skill-creator's SKILL.md to every prompt. That file exceeds the Windows command-line limit, so it was omitted from the prompt. Grading used skill-creator's grader.md unchanged.
- The token totals in the summary table show 0 and are unreliable.
- Eval 8 is a should-not-trigger case. The runner always tells the agent to read the skill first, so this case cannot measure non-triggering. It scored 1/2 in one run and 0/2 in the others, because the answer pointed at `./install.sh mcp register`.
- Eval 3 with skill lost one expectation in every run because no single command combined `--model-hub ollama` and `--model qwen2.5:7b`.
- Eval 6 asks for `--keep-models`, because uninstall now deletes models by default.
- Eval 2 expects `HARNESS_LLM_MODEL` set to the exact served id and no `--model`, because for an external endpoint `--model` strips an `org/` prefix. This table is from the run after that change, with a SKILL.md that says the same.
- benchmark.json is not included. It stores the grader's quoted evidence, including unsafe commands from the without-skill answers, which security scanners flag.
