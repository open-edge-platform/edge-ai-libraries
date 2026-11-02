# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fillers for the `{tool_descriptions}` slot in the predictor prompt; selected
by `ToolCompressor.tool_descriptions_mode`:

  - DEFAULT_TOOL_DESCRIPTIONS — hardcoded OpenClaw catalogue (benchmark path).
  - build_dynamic_tool_descriptions(tools) — derived from each request's
    `tools` schema (per-request demo path).

Output: one line per tool, `- name: description` (or `- name` if empty).
"""
from __future__ import annotations


DEFAULT_TOOL_DESCRIPTIONS: str = """\
Available tools (name: description):
- read: Read text/image files (for PDF files, use exec to convert first)
- edit: Edit a file by replacing exact text (surgical find-and-replace)
- write: Write content to a file (create or overwrite)
- exec: Execute shell commands (list files, convert PDFs, run scripts, etc.)
- process: Manage running exec sessions (poll, kill, send input)
- browser: Control a web browser (navigate, screenshot, interact with pages)
- web_search: Search the web using DuckDuckGo
- web_fetch: Fetch and extract readable content from a URL
- canvas: Control node canvases (present/render UI)
- nodes: Discover and control paired devices
- cron: Manage scheduled jobs
- message: Send messages via channel plugins
- tts: Convert text to speech
- gateway: Restart or configure the gateway
- agents_list: List available agent IDs
- sessions_list: List active sessions
- sessions_history: Fetch message history for a session
- sessions_send: Send a message into another session
- sessions_yield: End current turn, wait for subagent results
- sessions_spawn: Spawn an isolated sub-agent session
- subagents: List/kill/steer spawned sub-agents
- session_status: Show session status card
"""


def build_dynamic_tool_descriptions(tools: list[dict] | None) -> str:
    """Render an OpenAI tools-schema array as a `name: description` block."""
    if not tools:
        return ""
    lines: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        func = tool.get("function", {})
        if not isinstance(func, dict):
            continue
        name = str(func.get("name", "")).strip()
        if not name:
            continue
        desc = str(func.get("description", "")).strip().replace("\n", " ")
        lines.append(f"- {name}: {desc}" if desc else f"- {name}")
    return "\n".join(lines)
