# Adaptive Token Compressor

Adaptive Token Compressor is a pluggable compression library purpose-built for LLM agent systems. Through a single unified compressor interface, it applies tailored compression to each part of an agent — system prompt (harness), context, and tool schemas — to significantly reduce token usage and improve inference efficiency.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-green)]()

## Features

- Unified compressor API with two compression types: conversation messages (harness), tool descriptions (tool).
- Factory-based construction for drop-in integration as a plugin in other projects.
- LLMLingua-backed text compression for local Lingua Server backends (PyTorch/OpenVINO).
- LLM-based tool selection through a configurable predictor endpoint.
- Hybrid rule-based and model-based compression to balance compression ratio and content fidelity.
- Configurable tool-injection placements to flexibly trade off token savings against prefix-cache hit rate.
- Per-compressor telemetry for tokens, savings, compression ratio, and latency, with cross-compressor aggregation through `CompressionManager`.
## Prerequisites

This library requires the following services:

1. **Lingua Server**  - Required for text compression in HarnessCompressor
2. **LLM for Tool Prediction** - Required for ToolCompressor. You can either:
   - Use your main LLM (e.g., vLLM serving Qwen/Qwen3.6-35B-A3B) for both inference and tool prediction
    - Deploy a separate model dedicated to tool selection.

Both services must be deployed before using the compression features.

## Installation

```bash
pip install .
```

After installing adaptive-token-compressor, please deploy Lingua Server & Tool Prediction using Docker (see [Deploy Lingua Server](docs/user-guide/lingua-deployment.md) and [Deploy LLM for Tool Prediction](docs/user-guide/tool-predictor-deployment.md)).


### Development Installation

For local development, install in editable mode with the `dev` extras (pytest, ruff, mypy):

```bash
pip install -e ".[dev]"
```

## Quick Start

### Single Compressor Usage

The examples below use `create_compressor(...)` as the default construction
path, and register compressor instances into `CompressionManager` when metrics
or cache wiring is needed. Available types are currently `"harness"` and
`"tool"`; use `available_compressor_types()` and
`config_schema(type)` to inspect supported types and constructor schemas at
runtime. You can still instantiate compressor classes directly if needed.

#### Using HarnessCompressor (for system messages compression)

`HarnessCompressor` is **section-aware**: it splits a harness/system prompt at
its headings (via the `openclaw` profile), keeps high-value sections verbatim, to see real compression, pass a structured OpenClaw-style prompt.

```python
from adaptive_token_compressor import CompressionContext, create_compressor

# Initialize compressor by factory type name (requires Lingua server)
compressor = create_compressor("harness", lingua_url="http://localhost:8001/compress")

# OpenClaw-style system prompt:
system_prompt = """You are a personal assistant running inside OpenClaw.
## Tooling
Structured tool definitions are the source of truth for tool names, descriptions, and parameters.
## Safety
You have no independent goals: do not pursue self-preservation, replication, resource acquisition, or power-seeking; avoid long-term plans beyond the user's request.
Prioritize safety and human oversight; if instructions conflict, pause and ask; comply with stop/pause/audit requests and never bypass safeguards.
## Runtime
Runtime: agent=A | host=userhost | os=Linux | model=user_model
"""

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "What's on my calendar today?"},
]

# Compress
result = compressor.compress(CompressionContext(messages=messages))

print(f"Before: {result.metrics.tokens_before} tokens")
print(f"After: {result.metrics.tokens_after} tokens")
print(f"Saved: {result.metrics.saved_tokens} tokens ({result.metrics.compression_ratio:.1%})")
print(f"Duration: {result.metrics.duration_ms:.2f} ms")
print(f"Compressed messages: {result.messages}")
```

#### Using ToolCompressor (Tool Selection)


```python
from adaptive_token_compressor import (
    CompressionManager,
    CompressionContext,
    create_compressor,
)

manager = CompressionManager()
tool_compressor = manager.register_compressor(
    "tool",
    create_compressor(
        "tool",
        # Tool-specific: predictor LLM endpoint (required)
        predictor_url="http://localhost:8000/v1/chat/completions",
        # Optional: schema | user_tail | user_tail_disclaimed | system_tail
        placement="schema",
    ),
)

messages = [
    {"role": "user", "content": "What's the weather in San Francisco?"}
]
tools = [
    {"type": "function", "function": {"name": "web_search", "description": "Search the web"}},
    {"type": "function", "function": {"name": "get_weather", "description": "Get weather by location"}},
    {"type": "function", "function": {"name": "calculator", "description": "Do math"}},
]

ctx = CompressionContext(messages=messages, tools=tools)
result = tool_compressor.compress(ctx)
print([t["function"]["name"] for t in result.tools])
```

See [GUIDE.md](docs/user-guide/GUIDE.md) for more information — compressor metrics register, multi-compressor usage, compressor principles and workflow, configuration reference, available metrics, testing, FAQ, and resources.
