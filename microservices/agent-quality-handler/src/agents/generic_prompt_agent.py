# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generic, config-only specialist agent.

The 4 built-in specialists (policy/analysis/evidence/ticketing) each have a
bespoke module because they apply different data-shaping/business logic.
Many additional specialists an integrator wants to register, though, are
"just" a prompt: fetch the current detection summary, add whatever upstream
agents' outputs this agent depends on, ask the configured LLM a
use-case-specific question, and return its answer.

Pointing an ``agent_registry`` entry's ``module`` at this file covers that
case with **zero new Python** — only ``agents.yaml`` (for the registry entry
and optional per-agent config block) and the use-case prompt file (for a
new ``[SECTION]``) need to change. See ``AgentContext.agent_name``/
``.prompt_section``/``.agent_config()`` for how this module identifies which
registry entry it is being invoked as, since it is shared by any number of
them.

In fallback mode (no LLM configured) this agent cannot run arbitrary
instructions, so it returns a deterministic echo of the inputs it would
otherwise have sent to the model, tagged ``"mode": "fallback"``.
"""

import json
import logging
from typing import Any

from ..utility import llm_client, storage_client, prompt_loader
from .context import AgentContext

log = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 512
_FALLBACK_SYSTEM_PROMPT = (
    "You are a quality-assurance assistant analyzing defect detection data."
)


def run(context: AgentContext) -> dict[str, Any]:
    """Run a config-only, prompt-driven agent identified by ``context.agent_name``."""
    agent_name = context.agent_name or "generic_prompt_agent"
    agent_cfg = context.agent_config()

    summary = storage_client.get_summary(min_id=context.min_id, max_id=context.max_id) or {}
    if not isinstance(summary, dict):
        summary = {}

    if llm_client.is_fallback_mode():
        return _fallback_result(agent_name, summary, context.upstream_results)

    system_prompt = _resolve_section(
        context, "SYSTEM", default=_FALLBACK_SYSTEM_PROMPT
    )
    instructions = _resolve_section(
        context,
        context.prompt_section or agent_name.upper(),
        default=agent_cfg.get(
            "instructions",
            f"Review the data below for the '{agent_name}' use case and report findings.",
        ),
    )

    user_message = _build_user_message(instructions, summary, context.upstream_results)
    max_tokens = int(agent_cfg.get("max_tokens", _DEFAULT_MAX_TOKENS))
    raw = llm_client.call_llm(
        system_prompt=system_prompt, user_message=user_message, max_tokens=max_tokens
    )
    log.info("%s agent LLM response received (%d chars)", agent_name, len(raw))

    return {
        "agent": agent_name,
        "mode": "llm",
        "output": _try_parse_json(raw),
        "summary": summary,
        "upstream_used": sorted(context.upstream_results),
    }


def _resolve_section(context: AgentContext, section: str, *, default: str) -> str:
    """Return ``[section]`` from the use-case prompt file, or ``default`` if absent."""
    if not section:
        return default
    try:
        return prompt_loader.get_section(context.use_case_id, section, context.prompts_dir)
    except (FileNotFoundError, KeyError) as exc:
        log.warning(
            "%s: prompt section [%s] unavailable (%s); using configured default",
            context.agent_name or "generic_prompt_agent",
            section,
            exc,
        )
        return default


def _build_user_message(
    instructions: str, summary: dict, upstream_results: dict[str, dict]
) -> str:
    lines = [instructions, "", "Detection summary (JSON):", json.dumps(summary, indent=2)]
    if upstream_results:
        lines.extend(
            [
                "",
                "Upstream agent results (JSON):",
                json.dumps(upstream_results, indent=2, default=str),
            ]
        )
    return "\n".join(lines)


def _try_parse_json(raw: str) -> Any:
    """Return ``raw`` parsed as JSON when possible, otherwise the raw text."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _fallback_result(
    agent_name: str, summary: dict, upstream_results: dict[str, dict]
) -> dict[str, Any]:
    return {
        "agent": agent_name,
        "mode": "fallback",
        "summary": summary,
        "upstream_used": sorted(upstream_results),
        "note": (
            "No LLM configured (LLM_MODE=fallback); generic_prompt_agent cannot "
            "evaluate custom instructions without a model, so this is a "
            "deterministic echo of the inputs it would have sent."
        ),
    }
