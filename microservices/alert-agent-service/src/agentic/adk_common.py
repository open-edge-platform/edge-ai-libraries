# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional, Tuple

from src.config import settings

logger = logging.getLogger(__name__)

_adk_available: Optional[bool] = None


def is_adk_available() -> bool:
    """Check whether google-adk can be imported."""
    global _adk_available
    if _adk_available is None:
        try:
            import google.adk  # noqa: F401
            _adk_available = True
        except ImportError:
            _adk_available = False
    return _adk_available


def create_adk_model():
    """
    Create a LiteLlm model instance pointing at the local OVMS endpoint.

    Returns a configured LiteLlm object.
    Raises RuntimeError if LLM_URL is not set.
    """
    from google.adk.models.lite_llm import LiteLlm

    if not settings.LLM_URL:
        raise RuntimeError("LLM_URL is not set — cannot create ADK model")

    os.environ.setdefault("LITELLM_PROXY_API_KEY", "local")
    os.environ.setdefault("LITELLM_PROXY_API_BASE", settings.LLM_URL)
    LiteLlm.use_litellm_proxy = True

    model = LiteLlm(model=f"litellm_proxy/{settings.LLM_MODEL}", tool_choice="auto")
    logger.debug(
        f"Created ADK model (url={settings.LLM_URL} model={settings.LLM_MODEL})"
    )
    return model


def create_runner(agent, app_name: str, session_service=None):
    """
    Create an ADK Runner and InMemorySessionService for an agent.

    Parameters
    ----------
    agent : LlmAgent
    app_name : str
    session_service : InMemorySessionService, optional
        Reuse an existing service to preserve sessions across tool refreshes.

    Returns
    -------
    (Runner, InMemorySessionService)
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    if session_service is None:
        session_service = InMemorySessionService()

    runner = Runner(
        agent=agent,
        app_name=app_name,
        session_service=session_service,
    )
    return runner, session_service


async def run_agent_prompt(
    runner,
    session_service,
    session_id: str,
    prompt: str,
    timeout: float = 10.0,
    known_sessions: Optional[set] = None,
    user_id: str = "system",
    app_name: str = "alert-agent-service",
) -> Tuple[str, List[str]]:
    """
    Send a prompt to an ADK agent and collect text response + tool call names.

    Creates the session if it doesn't exist yet, runs the agent in a thread
    pool (Runner.run is synchronous), and extracts text responses and tool
    call names from the event stream.

    Returns
    -------
    (text_response, tool_names_called)
    """
    if known_sessions is None:
        known_sessions = set()

    if session_id not in known_sessions:
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        known_sessions.add(session_id)

    def _run():
        from google.genai import types

        events = runner.run(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                parts=[types.Part(text=prompt)]
            ),
        )
        text_parts = []
        tool_calls = []
        for event in events:
            if hasattr(event, "tool_call") and event.tool_call:
                tool_calls.append(event.tool_call.name)
            if hasattr(event, "content") and event.content:
                for part in event.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        text_parts.append(part.text)
        return "".join(text_parts), tool_calls

    text_response, tool_names = await asyncio.wait_for(
        asyncio.to_thread(_run),
        timeout=timeout,
    )
    return text_response, tool_names
