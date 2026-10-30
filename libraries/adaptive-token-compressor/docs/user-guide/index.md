# Adaptive Token Compressor

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/adaptive-token-compressor/README.md">
     Readme
  </a>
</div>
hide_directive-->

Adaptive Token Compressor is a pluggable Python library purpose-built for LLM
agent systems. Through a single unified compressor interface it applies tailored
compression to each part of an agent pipeline — system prompt (harness), tool
schemas, and conversation context — to significantly reduce token usage and
improve inference efficiency on edge hardware.

## Use Cases

- Reducing LLM inference cost in agentic pipelines with large system prompts or
  tool catalogs.
- Compressing tool schemas at runtime so only contextually relevant tools are
  included in the prompt.
- Compressing long conversation history and tool outputs in multi-turn agent
  sessions.
- Tracking per-compressor and cross-compressor token savings, latency, and
  compression ratio telemetry.
- Drop-in integration into existing agent frameworks via a factory-based
  compressor API.

## Key Capabilities

- **Unified compressor API** with three specialized types: `harness`
  (conversation messages and system prompt), `tool` (tool schema selection),
  and `context` (experimental history and tool-output compression).
- **HarnessCompressor** — section-aware message compression using hybrid
  rule-based and model-based compression; preserves instruction-critical
  content while reducing token cost.
- **ToolCompressor** — LLM-guided or reranker-based tool selection that scores
  and filters tool schemas from conversation context, with configurable
  injection placements to trade off token savings against prefix-cache hit rate.
- **ContextCompressor (Experimental)** — turn-aware optimization for long,
  tool-heavy conversations. It organizes history around tool-interaction turns,
  keeping tool calls and their results connected while applying selective
  compression across older turns. Recent-turn retention, recovery-guided
  historical stubs, and optional edit-aware safeguards help maintain continuity
  as the conversation evolves. Eligible content can also be compressed through
  Claw Compactor or Compress Server.
- **Compress Server runtimes** — supports PyTorch and OpenVINO runtimes for the
  compression service, including Intel GPU (XPU) acceleration.
- **CompressionManager** — orchestrates multiple compressors in a single
  pipeline and provides cross-compressor metric aggregation (tokens saved,
  compression ratio, average latency per request).
- **Multi-key metrics aggregation** — independently track metrics by provider,
  user, or other application-defined dimensions alongside global metrics,
  with per-key snapshots through `CompressionManager`.
- **Factory construction** — create and inspect compressors by type name at
  runtime using `create_compressor()`, `available_compressor_types()`, and
  `config_schema()`.

## Get Started

If you want to reduce token usage and improve inference efficiency,
start here with the basics:

- [Installation](./get-started.md#installation)
  — set up the library and required dependencies.
- [Quick Start](./get-started.md#quick-start)
  — run your first compression workflow in just a few steps.

Once it is up and running, explore the full
[Get Started guide](./get-started.md) for configuration options, compressor
principles and workflow, compressor metrics, single- and multi-compressor
metrics collection, testing, and additional resources.

## Next Steps

- [Deploy Compress Server](./compress-server-deployment.md) — set up the
  compress server required by HarnessCompressor and ContextCompressor.
- [Deploy LLM for Tool Prediction](./tool-predictor-deployment.md) — set up
  the predictor service required by ToolCompressor.
- [Release Notes](./release-notes.md) — version history and changelog.

<!--hide_directive
:::{toctree}
:hidden:

get-started
compress-server-deployment
tool-predictor-deployment
Release Notes <./release-notes.md>

:::
hide_directive-->
