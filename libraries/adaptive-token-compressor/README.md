# Adaptive Token Compressor

Adaptive Token Compressor is a pluggable compression library purpose-built for
LLM agent systems. Through a single unified compressor interface, it applies
tailored compression to each part of an agent — system prompt (harness), tool
schemas, and context — to significantly reduce token usage and improve
inference efficiency.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-green)]()

## Features

- Unified compressor API with three compression types: conversation messages
  (harness), tool descriptions (tool), and experimental context compression
  (context).
- Factory-based construction for drop-in integration as a plugin
  in other projects.
- Model-based text compression via a local Compress Server (PyTorch/OpenVINO).
- Hybrid rule-based and model-based compression to balance compression ratio
  and content fidelity.
- Experimental turn-aware context optimization that preserves tool-call/result
  associations, with recent-turn protection, recovery-guided stubs for oversized
  historical results, and optional edit-aware preservation of file reads.
- Tool selection through a configurable LLM or lightweight reranker endpoint
  for lower predictor latency.
- Fine-grained tool-selection controls for ranking, tool-count guidance, and
  predictor input/output token budgets.
- Configurable tool-injection placements to flexibly trade off token savings
  against prefix-cache hit rate.
- Configurable context compression through Claw Compactor or Compress Server,
  with content-aware routing for eligible tool results.
- Digit protection for numerical values and their surrounding context.
- Per-compressor telemetry for tokens, savings, compression ratio, and latency,
  with cross-compressor aggregation through `CompressionManager`.
- Multi-key metrics aggregation for independent views by provider, user, or
  other application-defined dimensions, alongside global metrics.

## Get Started

If you want to reduce token usage and improve inference efficiency,
start here with the basics:

- [Installation](./docs/user-guide/get-started.md#installation)
  — set up the library and required dependencies.
- [Quick Start](./docs/user-guide/get-started.md#quick-start)
  — run your first compression workflow in just a few steps.

Once it is up and running, explore the full
[Get Started guide](./docs/user-guide/get-started.md) for configuration options,
compressor principles and workflow, compressor metrics, single- and
multi-compressor metrics collection, testing, and additional resources.
