# Adaptive Token Compressor

Adaptive Token Compressor is a pluggable compression library purpose-built for LLM agent systems. Through a single unified compressor interface, it applies tailored compression to each part of an agent — system prompt (harness), context, and tool schemas — to significantly reduce token usage and improve inference efficiency. 

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-green)]()

## Features

- Unified compressor API with three compression types: conversation messages (harness), tool descriptions (tool), and context content (context).
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

### Recommended Installation

```bash
pip install "adaptive-token-compressor[claw-compactor]"
```

Then deploy Lingua Server & Tool Prediction using Docker (see [Deploy Lingua Server](#deploy-lingua-server) and [Deploy LLM for Tool Prediction](#deploy-llm-for-tool-prediction) below).



### Minimal Installation (without Claw Compactor)

If you do not need Claw Compactor locally:

```bash
pip install adaptive-token-compressor
```

**Without Claw Compactor**, HarnessCompressor will use basic Lingua compression only.

### Development Installation

```bash
pip install "adaptive-token-compressor[claw-compactor,dev]"
```

## Deploy Lingua Server

Use the dedicated deployment guide for exact compose commands, environment
variables, and backend selection (PyTorch/OpenVINO):

- [deployment/lingua/README.md](deployment/lingua/README.md)

Quick check after startup:

```bash
curl http://localhost:8001/health
```

For all available runtime knobs and defaults in this document, see
[Lingua Server Configuration](#lingua-server-configuration).

## Deploy LLM for Tool Prediction

ToolCompressor requires an LLM to predict relevant tools. You can either use your main LLM or deploy a dedicated smaller model.

**⚠️ Tested Models**: This library has been tested with  **Qwen/Qwen3.6-35B-A3B** for tool prediction. Other models may work but are not guaranteed to produce optimal results.

Use the dedicated deployment guide for exact compose instructions,
endpoint wiring, and portability notes:

- [deployment/tool_predictor/README.md](deployment/tool_predictor/README.md)

Quick check after startup:

```bash
curl http://<your-host>:<your-port>/v1/models
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

**With Metrics Collection (requires CompressionManager):**

```python
from adaptive_token_compressor import (
    CompressionManager,
    CompressionContext,
    create_compressor,
    CompressionRatio,
    TotalSaved
)

# Metrics collection requires using CompressionManager
manager = CompressionManager()

# Register compressor first
harness_compressor = manager.register_compressor(
    "harness",
    create_compressor("harness", lingua_url="http://localhost:8001/compress"),
)

# Then register metrics with names
manager.register_metric("compression_ratio", CompressionRatio(sources="harness"))
manager.register_metric("total_saved", TotalSaved(sources="harness"))

# Compress multiple requests
for i in range(5):
    messages = [...]  # Different messages each time
    ctx = CompressionContext(messages=messages)
    result = harness_compressor.compress(ctx)

# View aggregated metrics (returns dict with all registered metric names)
stats = manager.snapshot()
print(f"Compression ratio: {stats['compression_ratio']:.2%}")
print(f"Total saved: {stats['total_saved']} tokens")
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

### Multi-Compressor Usage with CompressionManager

Metrics support both **per-source** tracking (single source string) and **cross-compressor aggregation** (list of sources). Cross-compressor metrics let you track combined statistics — e.g. average duration per request across the harness and tool compressors together.

```python
from adaptive_token_compressor import (
    CompressionManager,
    CompressionContext,
    create_compressor,
    TotalSaved,
    AvgDurationPerRequest,
)

# Initialize manager
manager = CompressionManager()

# Register compressors first
harness_compressor = manager.register_compressor(
    "harness",
    create_compressor("harness", lingua_url="http://localhost:8001/compress"),
)
tool_compressor = manager.register_compressor(
    "tool",
    create_compressor(
        "tool",
        predictor_url="http://localhost:8000/v1/chat/completions",
    ),
)

# Register one per-source metric plus two aggregate metrics
manager.register_metric(
    "harness_saved",
    TotalSaved(sources="harness")
)
manager.register_metric(
    "total_saved_all",
    TotalSaved(sources=["harness", "tool"])
)
manager.register_metric(
    "avg_dur_per_request_all",
    AvgDurationPerRequest(sources=["harness", "tool"])
)

# Process multiple requests
for i in range(10):
    messages = [...]  # Different messages each time
    tools = [...]     # Full tool list

    # IMPORTANT: use the SAME req_id for all compressors in one request so
    # request_count() counts unique requests, not per-compressor calls. This
    # makes avg_dur_per_request_all = total duration / number of requests.
    req_id = f"req-{i}"

    ctx = CompressionContext(messages=messages, tools=tools)

    # Compress tools
    result = tool_compressor.compress(ctx, req_id=req_id)
    ctx = CompressionContext(messages=result.messages, tools=result.tools)

    # Compress messages
    result = harness_compressor.compress(ctx, req_id=req_id)

    # Use result.messages and result.tools for LLM inference

# View aggregated metrics (snapshot returns all registered metrics)
stats = manager.snapshot()

print(f"  Harness saved: {stats['harness_saved']} tokens")
print(f"  Total saved (all): {stats['total_saved_all']} tokens")
print(f"  Avg duration per request (all): {stats['avg_dur_per_request_all']:.1f} ms")
```

> **Note on PerRequest metrics** (`AvgDurationPerRequest`, `AvgSavedPerRequest`, etc.): these divide by the number of unique requests. You must either pass `req_id` to `compressor.compress(ctx, req_id=...)` (as above), or call `manager.set_per_anchor("<source>")` to use one compressor's call count as the request denominator. Without either, `manager.snapshot()` raises a `RuntimeError` (the denominator is checked at snapshot time, not at registration).

See [GUIDE.md](GUIDE.md) for more information — compressor principles and workflow, configuration reference, available metrics, testing, FAQ, and resources.
