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
pip install adaptive-token-compressor
```
After install  adaptive-token-compressor, please deploy Lingua Server & Tool Prediction using Docker (see [Deploy Lingua Server](docs/use-guide/lingua-deployment.md) and [Deploy LLM for Tool Prediction](docs/use-guide/tool-predictor-deployment.md)).


### Development Installation

```bash
pip install "adaptive-token-compressor[dev]"
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

```python
from adaptive_token_compressor import CompressionContext, create_compressor

# Initialize compressor by factory type name (requires Lingua server)
compressor = create_compressor("harness", lingua_url="http://localhost:8001/compress")

# Prepare conversation messages
messages = [
    {"role": "system", "content": "You are a helpful assistant..."},
    {"role": "user", "content": "What is machine learning?"},
    {"role": "assistant", "content": "Machine learning is a branch of AI..."}
]

# Create compression context
ctx = CompressionContext(messages=messages)

# Compress
result = compressor.compress(ctx)

print(f"Before: {result.metrics.tokens_before} tokens")
print(f"After: {result.metrics.tokens_after} tokens")
print(f"Saved: {result.metrics.saved_tokens} tokens")
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

See [GUIDE.md](docs/use-guide/GUIDE.md) for more information — compressor metrics register, multi-compressor usage, compressor principles and workflow, configuration reference, available metrics, testing, FAQ, and resources.
