# Adaptive Token Compressor

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/libraries/adaptive-token-compressor">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0//libraries/adaptive-token-compressor/README.md">
     Readme
  </a>
</div>
hide_directive-->

Adaptive Token Compressor is a pluggable Python library purpose-built for LLM agent systems. Through a single unified compressor interface it applies tailored compression to each part of an agent pipeline — system prompt (harness), conversation context, and tool schemas — to significantly reduce token usage and improve inference efficiency on edge hardware.

## Use Cases

- Reducing LLM inference cost in agentic pipelines with large system prompts or tool catalogs.
- Compressing tool schemas at runtime so only contextually relevant tools are included in the prompt.
- Tracking per-compressor and cross-compressor token savings, latency, and compression ratio telemetry.
- Drop-in integration into existing agent frameworks via a factory-based compressor API.

## Key Capabilities

- **Unified compressor API** with two specialised types: `harness` (conversation messages and system prompt) and `tool` (tool schema selection).
- **HarnessCompressor** — section-aware message compression using hybrid rule-based and LLMLingua-2 model-based compression; preserves instruction-critical content while reducing token cost.
- **ToolCompressor** — LLM-guided tool selection that scores and filters tool schemas from conversation context, with configurable injection placements to trade off token savings against prefix-cache hit rate.
- **Lingua Server backends** — supports PyTorch and OpenVINO backends for the Lingua compression service, including Intel GPU (XPU) acceleration.
- **CompressionManager** — orchestrates multiple compressors in a single pipeline and provides cross-compressor metric aggregation (tokens saved, compression ratio, average latency per request).
- **Factory construction** — create and inspect compressors by type name at runtime using `create_compressor()`, `available_compressor_types()`, and `config_schema()`.

## Next Steps

- [Deploy Lingua Server](./lingua-deployment.md) — set up the Lingua backend required by HarnessCompressor.
- [Deploy LLM for Tool Prediction](./tool-predictor-deployment.md) — set up the predictor service required by ToolCompressor.
- [Guide](./GUIDE.md) — metrics collection, multi-compressor pipelines, configuration reference, and FAQ.
- [Release Notes](./release-notes.md) — version history and changelog.

<!--hide_directive
:::{toctree}
:hidden:

lingua-deployment
tool-predictor-deployment
GUIDE
release-notes
:::
hide_directive-->
