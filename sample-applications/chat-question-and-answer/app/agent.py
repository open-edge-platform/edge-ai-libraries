# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Agentic ChatQnA extension using LangGraph ReAct agent.

This module adds an agentic layer on top of the existing ChatQnA RAG pipeline.
The agent has access to 3 tools it can choose from to answer a question:
  1. vector_search  – queries the existing PGVector knowledge base
  2. web_search     – does a lightweight DuckDuckGo search for live info
  3. calculator     – evaluates simple math expressions safely

The agent runs a ReAct (Reason + Act) loop: it picks tools, observes results,
and keeps going until it has enough info to write the final answer.
"""

import os
import ast
import math
import operator
import logging
from typing import AsyncIterator

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI as EGAIModelServing
from langgraph.prebuilt import create_react_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool 1 – Vector Search
# Wraps the existing PGVector retriever so the agent can use it as a tool.
# ---------------------------------------------------------------------------
@tool
async def vector_search(query: str) -> str:
    """
    Search the knowledge base using vector (semantic) similarity.
    Use this tool when the question is about topics likely covered
    in the uploaded documents.

    Args:
        query: The search query string.

    Returns:
        Relevant document snippets as a formatted string.
    """
    try:
        # Import here to avoid circular imports and to keep the tool lazy
        from .chain import retriever

        docs = await retriever.aget_relevant_documents(query)
        if not docs:
            return "No relevant documents found in the knowledge base."

        results = []
        for i, doc in enumerate(docs, 1):
            content = doc.page_content.strip()
            source = doc.metadata.get("source", "unknown")
            results.append(f"[{i}] {content}\n   Source: {source}")

        return "\n\n".join(results)

    except Exception as e:
        logger.error(f"vector_search failed: {e}")
        return f"Vector search encountered an error: {str(e)}"


# ---------------------------------------------------------------------------
# Tool 2 – Web Search
# Uses DuckDuckGo (no API key needed) for live, real-world information.
# Falls back gracefully if duckduckgo_search is not installed.
# ---------------------------------------------------------------------------
@tool
def web_search(query: str) -> str:
    """
    Search the web using DuckDuckGo to find recent or general information
    that may not be in the knowledge base.
    Use this for current events, factual lookups, or anything outside
    the uploaded documents.

    Args:
        query: The search query string.

    Returns:
        Top web search results as a formatted string.
    """
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=3):
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                results.append(f"• {title}\n  {body}\n  Link: {href}")

        if not results:
            return "No web results found."

        return "\n\n".join(results)

    except ImportError:
        return (
            "Web search is not available. "
            "Install duckduckgo-search: pip install duckduckgo-search"
        )
    except Exception as e:
        logger.error(f"web_search failed: {e}")
        return f"Web search encountered an error: {str(e)}"


# ---------------------------------------------------------------------------
# Tool 3 – Calculator
# Safely evaluates simple math without using eval() on arbitrary code.
# ---------------------------------------------------------------------------

# Whitelist of allowed AST node types for the safe evaluator
_SAFE_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.FloorDiv,
    ast.USub,
    ast.UAdd,
    ast.Num,
    ast.Constant,  # ast.Num kept for Python <3.8 compat
    ast.Call,
    ast.Name,  # allow math functions like sqrt, log
)

_ALLOWED_NAMES = {
    name: getattr(math, name) for name in dir(math) if not name.startswith("_")
}
_ALLOWED_NAMES.update(
    {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
    }
)


def _safe_eval(node):
    """Recursively evaluates a whitelisted AST node."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value}")
    elif isinstance(node, ast.Num):  # Python < 3.8
        return node.n
    elif isinstance(node, ast.BinOp):
        ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
            ast.FloorDiv: operator.floordiv,
        }
        op = ops.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op)}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_safe_eval(node.operand)
        elif isinstance(node.op, ast.UAdd):
            return +_safe_eval(node.operand)
        raise ValueError(f"Unsupported unary: {node.op}")
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls allowed")
        func_name = node.func.id
        if func_name not in _ALLOWED_NAMES:
            raise ValueError(f"Function not allowed: {func_name}")
        args = [_safe_eval(a) for a in node.args]
        return _ALLOWED_NAMES[func_name](*args)
    elif isinstance(node, ast.Name):
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        raise ValueError(f"Name not allowed: {node.id}")
    else:
        raise ValueError(f"Unsupported node type: {type(node)}")


@tool
def calculator(expression: str) -> str:
    """
    Evaluate a mathematical expression and return the numeric result.
    Supports basic arithmetic (+, -, *, /, **, %), and math functions
    like sqrt(), log(), sin(), cos(), etc.

    Examples:
        "2 ** 10"        → 1024
        "sqrt(144)"      → 12.0
        "(5 + 3) * 2.5"  → 20.0

    Args:
        expression: A valid math expression as a string.

    Returns:
        The computed result as a string, or an error message.
    """
    try:
        expression = expression.strip()
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as e:
        return f"Could not evaluate '{expression}': {str(e)}"


# ---------------------------------------------------------------------------
# Agent Factory
# ---------------------------------------------------------------------------

TOOLS = [vector_search, web_search, calculator]

SYSTEM_PROMPT = """You are a helpful AI assistant with access to three tools:
1. vector_search – find information from the uploaded knowledge base documents
2. web_search    – search the internet for information not in the knowledge base
3. calculator    – evaluate math expressions

Think step-by-step about which tool (if any) will best answer the question.
You can call multiple tools in sequence. Once you have enough information,
give a clear, concise final answer.
Always cite where your information came from (document source or web link).
"""


def build_agent():
    """
    Build and return a LangGraph ReAct agent using the configured LLM.
    The agent shares the same LLM endpoint as the main ChatQnA pipeline.
    """
    endpoint_url = os.getenv("ENDPOINT_URL", "http://localhost:8080")
    llm_model = os.getenv("LLM_MODEL", "Intel/neural-chat-7b-v3-3")

    llm = EGAIModelServing(
        openai_api_key="EMPTY",
        openai_api_base=endpoint_url,
        model_name=llm_model,
        temperature=0.01,
        top_p=0.99,
        streaming=True,
    )

    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
        state_modifier=SYSTEM_PROMPT,
    )

    return agent


async def run_agent_stream(question: str, history: str = "") -> AsyncIterator[str]:
    """
    Run the ReAct agent and yield SSE-formatted chunks.

    Emits two kinds of events:
      - "data: [agent] <thought/tool info>\n\n"  – intermediate agent steps
      - "data: <answer token>\n\n"               – final streamed answer

    Args:
        question: The user's question.
        history:  Conversation history as a plain string.

    Yields:
        SSE-formatted strings.
    """
    agent = build_agent()

    messages = []
    if history:
        messages.append(
            {"role": "system", "content": f"Conversation so far:\n{history}"}
        )
    messages.append({"role": "user", "content": question})

    try:
        async for event in agent.astream_events(
            {"messages": messages},
            version="v1",
        ):
            kind = event.get("event", "")

            # Agent picks a tool → tell the UI which tool is being called
            if kind == "on_tool_start":
                tool_name = event.get("name", "tool")
                tool_input = event.get("data", {}).get("input", {})
                query = tool_input.get("query") or tool_input.get("expression", "")
                yield f"data: [agent] 🔧 Using tool: **{tool_name}**({query!r})\n\n"

            # Tool finished → show a brief observation summary
            elif kind == "on_tool_end":
                tool_name = event.get("name", "tool")
                output = event.get("data", {}).get("output", "")
                preview = str(output)[:120].replace("\n", " ")
                yield f"data: [agent] ✅ {tool_name} result: {preview}...\n\n"

            # Final LLM answer tokens (streaming)
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield f"data: {chunk.content}\n\n"

    except Exception as e:
        logger.error(f"Agent run failed: {e}")
        yield f"data: [ERROR] Agent encountered an error: {str(e)}\n\n"
