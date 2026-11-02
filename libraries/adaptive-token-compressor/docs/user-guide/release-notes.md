# Release Notes: Adaptive Token Compressor

## Version 2026.3

**Release Date:** TBD

**Summary**:

Adds an experimental third compressor type for conversation context, and supports a small reranker model in the tool compressor for faster tool selection.

**New**:

- **Experimental:** `ContextCompressor` (`"context"` compressor type) optimizes long, tool-heavy
  conversation histories through turn-aware policies and selective
  compression, using tool-interaction boundaries to retain recent turns and
  process older content while preserving call-result associations.
  It replaces eligible oversized
  historical results with recovery-guided stubs, and can preserve reads of
  files later changed in the conversation. Remaining eligible content can be
  routed through Claw Compactor or Compress Server.
- Small-model tool selection with `Qwen/Qwen3-Reranker-0.6B` (`predictor_backend="reranker"`): about 10x lower predictor latency than the default `Qwen/Qwen3.6-35B-A3B` configuration, at a lower tool-token saving
- New `ToolCompressor` parameters `top_k`, `tool_count_level`, `predictor_max_output_tokens`, and `predictor_max_input_tokens`
- Multi-key metrics aggregation in `CompressionManager`: declare `metrics_keys` when registering a compressor (for example, `["provider", "user"]`) and pass `metrics_values` to `compress()` to aggregate metrics independently by each key's values; retrieve results with `snapshot(key=..., value=...)` or `snapshot_by_keys()`.

**Upgrade Notes**:

- `Avg*PerRequest` metrics now divide by the unique requests that went through the metric's own `sources`, instead of all requests seen by the `CompressionManager`. Requests that did not call any of the metric's compressors no longer lower its average, and `snapshot()` and `snapshot(source=...)` return the same value for the same metric. Values change only when some requests skip some compressors. Without `req_id` from the metric's sources, the `set_per_anchor()` call count is still the denominator.
- `CompressionManager.snapshot(source=...)` now selects metrics by the compressor they track instead of by metric name: it returns the metrics registered with `sources` set to the given compressor's registered name, whatever the metric names are. Metrics named `<name>.<metric>` that track only that compressor are returned as before. Metrics that track several compressors, and `RequestCount` metrics, are no longer returned even if their names start with `<name>.`; read them with `snapshot()`.


## Version 2026.2

**Release Date:** September 9, 2026

**Summary**:

Initial release of the Adaptive Token Compressor — a pluggable compression library purpose-built for LLM agent systems. Using a single unified interface, it compresses system prompts, context, and tool schemas across an LLM agent pipeline to reduce token usage and improve inference efficiency.

**Features**:

- Unified compressor API with two compression types: conversation messages (harness) and tool descriptions (tool)
- Factory-based construction for drop-in integration as a plugin in other projects
- LLMLingua-backed text compression for local Lingua Server backends (PyTorch/OpenVINO)
- LLM-based tool selection through a configurable predictor endpoint
- Hybrid rule-based and model-based compression to balance compression ratio and content fidelity
- Configurable tool-injection placements to flexibly trade off token savings against prefix-cache hit rate
- Per-compressor telemetry for tokens, savings, compression ratio, and latency, with cross-compressor aggregation through `CompressionManager`
