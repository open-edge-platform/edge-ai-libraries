# Release Notes

## Version: 2026.2

**Summary**

 Initial release of the Adaptive Token Compressor - a pluggable compression library purpose-built for LLM agent systems. Using a single unified interface, it compresses system prompts, context, and tool schemas across an LLM agent pipeline to reduce token usage and improve inference efficiency.

### Features

- Unified compressor API with two compression types: conversation messages (harness) and tool descriptions (tool)
- Factory-based construction for drop-in integration as a plugin in other projects
- LLMLingua-backed text compression for local Lingua Server backends (PyTorch/OpenVINO)
- LLM-based tool selection through a configurable predictor endpoint
- Hybrid rule-based and model-based compression to balance compression ratio and content fidelity
- Configurable tool-injection placements to flexibly trade off token savings against prefix-cache hit rate
- Per-compressor telemetry for tokens, savings, compression ratio, and latency, with cross-compressor aggregation through `CompressionManager`
