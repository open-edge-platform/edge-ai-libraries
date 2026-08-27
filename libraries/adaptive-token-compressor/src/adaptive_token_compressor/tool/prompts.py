# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Prompt templates + builders for the tool predictor.

Templates (each with one `{tool_descriptions}` slot):
  - FOCUS_FIVE_TOOL_PROMPT — for simple tasks (e.g. pinchbench): strict
    "5-10 tools"; self-contained, pair with build_static_prediction_prompt.
  - BASE_PROMPT — for complex tasks (e.g. ecrag demo): "3-5 tools" header
    only; pair with build_dynamic_prediction_prompt, which appends
    skills / call_history / skill_content sections + rules tail.
"""
from __future__ import annotations

import re

FOCUS_FIVE_TOOL_PROMPT: str = """\
Predict which tools are needed for a task. Rate each tool 1-5 (5=must have, 1=unlikely).

{tool_descriptions}

Output JSON only:
{{"toolname1": 5, "toolname2": 4, "toolname3": 3, "toolname4": 2, "toolname5": 1}}

*** CRITICAL: You MUST return EXACTLY 5 to 10 tools. NEVER return fewer than 5. ***
If only 2-3 tools are obviously needed, you MUST still fill up to 5 by adding auxiliary tools with lower scores.
Common fallback tools to add when you need more: exec (score 2), read (score 1), write (score 1), web_search (score 1), browser (score 1).

Scoring:
- 5 = Core tool directly required by the task
- 4 = Very likely supporting tool (e.g., write to save results)
- 3 = Alternative or auxiliary tool
- 2 = Might be useful in some scenarios
- 1 = Unlikely but remotely possible

Other rules:
- If the task requires editing/modifying a file (edit or write), MUST also include read
- Return ONLY valid JSON, no markdown, no explanation

Example - task "search the web for Python tutorials":
{{"web_search": 5, "browser": 4, "web_fetch": 3, "read": 2, "exec": 1}}
Note: even though only web_search is core, we still return 5 tools total."""


BASE_PROMPT: str = """\
Predict which tools an AI agent will need. Rate each tool 1-5 (5=must have, 1=unlikely).

Available tools:
{tool_descriptions}"""


# Rules block appended by `build_dynamic_prediction_prompt`.
# 5-7 floor + score-2 fallback tier + explicit fallback list closes systematic
# misses observed under dynamic prompt mode (e.g. PDF tasks dropping `exec`,
# single-turn main-agent calls dropping the one tool actually invoked).
# Validated on pinchbench gt coverage (95.5% → 100%) and ecrag invoked
# coverage (main agent 80% → 100%); ~+30 ms (+3%) mean predictor latency.
_DYNAMIC_RULES_TAIL: str = (
    '\nOutput JSON only: {"toolname": score, ...}\n'
    "\nRules:\n"
    "- Score 5: Core tools directly required\n"
    "- Score 4: Very likely supporting tools\n"
    "- Score 3: Alternative or auxiliary tools\n"
    "- Score 2: Fallback tools (e.g. exec for PDF, read for editing)\n"
    "- You MUST include 5-7 tools (3-4 core + 1-3 fallback)\n"
    "- If editing/modifying a file, MUST also include read\n"
    "- If the task says the agent is running as a subagent, include sessions_yield when completing the assigned task, when results auto-announce, or when control must be returned to the requester/main agent\n"
    "- If the task requires spawning or coordinating a subagent, include sessions_spawn; if that flow then waits for descendant results or hands control back, also include sessions_yield\n"
    "- Common fallbacks: exec (running shell, converting PDFs), "
    "read (loading files), write (saving results)\n"
    "- Return ONLY JSON, no markdown"
)

# Hint injected once into a SKILL.md excerpt that mentions "Sub-agent".
_SUBAGENT_HINT: str = (
    "⚠️ **必须调用sessions_spawn 来执行sub-agent；如果需要把控制权交回请求方或等待子代理结果，"
    "必须包含sessions_yield；当subagent任务完成并返回主agent时，必须调用sessions_yield作为回转标志** ⚠️"
)
_SUBAGENT_HINT_RE: re.Pattern[str] = re.compile(r"(Sub-agent[^\n]*)")


def build_static_prediction_prompt(
    *,
    template: str,
    tool_descriptions: str,
) -> str:
    """Fill the `{tool_descriptions}` slot; the template carries its own rules."""
    return template.format(tool_descriptions=tool_descriptions)


def build_dynamic_prediction_prompt(
    *,
    template: str,
    tool_descriptions: str,
    skills: list[tuple[str, str]] | None = None,
    call_history: list[dict] | None = None,
    skill_content: str | None = None,
) -> str:
    """Fill the template + append dynamic context sections + rules tail.

    Order: tool_descriptions → SKILL.md excerpt (if skill_content)
    OR skills list (if skills) → call_history → rules tail.
    """
    head = template.format(tool_descriptions=tool_descriptions)

    skills_section = ""
    if skill_content:
        injected = _SUBAGENT_HINT_RE.sub(
            r"\1\n" + _SUBAGENT_HINT,
            skill_content,
            count=1,
        )
        skills_section = (
            "\nThe agent has read a SKILL.md file. "
            "Based on the skill content below, predict which tools "
            "are needed for the NEXT step.\n"
            f"--- SKILL.md excerpt ---\n{injected}\n---"
        )
    elif skills:
        skill_lines = "\n".join(
            f"  - {name}: {desc}" for name, desc in skills
        )
        skills_section = (
            f"\nAgent has the following available skills:\n"
            f"{skill_lines}\n"
            "\nIMPORTANT: If the user task matches a skill's description, "
            "the agent will call `read` to load that skill's SKILL.md. "
            "You MUST include `read` in your prediction."
        )

    history_section = ""
    if call_history:
        history_lines: list[str] = []
        for i, call in enumerate(call_history, 1):
            args_brief = ""
            args = call.get("args")
            if isinstance(args, dict) and args:
                parts: list[str] = []
                for k, v in list(args.items())[:2]:
                    v_str = str(v)
                    if len(v_str) > 60:
                        v_str = v_str[:60] + "..."
                    parts.append(f"{k}={v_str}")
                args_brief = ", ".join(parts)
            result_brief = call.get("result_preview", "") or ""
            if len(result_brief) > 80:
                result_brief = result_brief[:80] + "..."
            entry = f"  {i}. {call.get('name', '')}({args_brief})"
            if result_brief:
                entry += f" -> {result_brief}"
            history_lines.append(entry)
        history_section = (
            "\nCompleted tool calls so far:\n"
            + "\n".join(history_lines)
            + "\n\nBased on the progress above, predict tools needed "
            "for the NEXT step (not tools already used, unless reuse is likely)."
        )

    return head + skills_section + history_section + "\n" + _DYNAMIC_RULES_TAIL
