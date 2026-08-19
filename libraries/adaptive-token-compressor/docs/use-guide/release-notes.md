# Release Notes

## Current Release

**Version**: 2026.2

This is the first release for adaptive-token-compressor. It is a pluggable compression library purpose-built for LLM agent systems. Through a single unified compressor interface, it applies tailored compression to each part of an agent — system prompt (harness), context, and tool schemas — to significantly reduce token usage and improve inference efficiency.

### Features

- Unified compressor API with two compression types: conversation messages (harness) and tool descriptions (tool)
- Factory-based construction for drop-in integration as a plugin in other projects.
- LLMLingua-backed text compression for local Lingua Server backends (PyTorch/OpenVINO).
- LLM-based tool selection through a configurable predictor endpoint.
- Hybrid rule-based and model-based compression to balance compression ratio and content fidelity.
- Configurable tool-injection placements to flexibly trade off token savings against prefix-cache hit rate.
- Per-compressor telemetry for tokens, savings, compression ratio, and latency, with cross-compressor aggregation through `CompressionManager`.
