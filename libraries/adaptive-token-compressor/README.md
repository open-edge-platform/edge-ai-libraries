# Adaptive Token Compressor

Adaptive Token Compressor is a pluggable compression library purpose-built for
LLM agent systems. Through a single unified compressor interface, it applies
tailored compression to each part of an agent — system prompt (harness), context,
and tool schemas — to significantly reduce token usage and
improve inference efficiency.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-green)]()

## Features

- Unified compressor API with two compression types: conversation messages
  (harness), tool descriptions (tool).
- Factory-based construction for drop-in integration as a plugin
  in other projects.
- LLMLingua-backed text compression for local Lingua Server backends
  (PyTorch/OpenVINO).
- LLM-based tool selection through a configurable predictor endpoint.
- Hybrid rule-based and model-based compression to balance compression ratio
  and content fidelity.
- Configurable tool-injection placements to flexibly trade off token savings
  against prefix-cache hit rate.
- Per-compressor telemetry for tokens, savings, compression ratio, and latency,
  with cross-compressor aggregation through `CompressionManager`.'

## Get Started

If you want to reduce token usage and improve inference efficiency,
start here with the basics:

- [Installation](./docs/user-guide/get-started.md#installation)
  — set up the library and required dependencies.
- [Quick Start](./docs/user-guide/get-started.md#quick-start)
  — run your first compression workflow in just a few steps.

Once it is up and running, explore the full
[Get Started guide](./docs/user-guide/get-started.md) for compressor metrics,
multi-compressor usage, workflow concepts, configuration options, testing, FAQ,
and additional resources.
