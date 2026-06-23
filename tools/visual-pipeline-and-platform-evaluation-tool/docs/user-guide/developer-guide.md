# Developer Guide

Use this guide to understand how ViPPET is built, how runtime data flows through the platform, and how to contribute
safely to the codebase.
It is intended for developers who need to work on the frontend, backend, metrics pipeline, or predefined workloads
rather than only use the product through the UI.

If you are looking for day-to-day usage instructions, start with the [User Guide](../user-guide/user-guide.md).
Use the Developer Guide when you want to understand internal architecture, inspect runtime behavior,
or make code and documentation changes.

## What this guide covers

The Developer Guide is organized around the main technical areas of the project:

**Architecture**: Learn how the ViPPET UI, backend, ONVIF discovery helper, and shared middleware services fit together
in the [Architecture](developer-guide/architecture.md) section.

**Performance Metrics**: Learn how pipeline-level FPS and latency data, together with system-level CPU, GPU, and NPU telemetry,
are collected and delivered in the [Performance Metrics](developer-guide/metrics.md) section.

**Contributing**: Learn how to navigate the repository, follow project conventions, and add new features, pipelines,
or elements in the [Contributing Guide](developer-guide/contributing-guide.md) section.

## Recommended path

If you are new to the codebase, this sequence works well:

1. Start with [Architecture](developer-guide/architecture.md) to understand the system boundaries and the role of each service.
2. Continue with [ViPPET UI](developer-guide/architecture/vippet-ui.md) and [ViPPET Backend](developer-guide/architecture/vippet-be.md)
for implementation details of the main application layers.
3. Review [Performance Metrics](developer-guide/metrics.md) to understand how runtime measurements are produced and consumed.
4. Finish with the [Contributing Guide](developer-guide/contributing-guide.md) before making changes to the codebase.

## When to use this guide

Use the Developer Guide when you want to:

- understand how requests, jobs, models, cameras, and metrics move through the system,
- inspect how the frontend and backend are structured internally,
- extend the platform with new pipelines or custom processing elements,
- trace where performance and telemetry data come from,
- prepare a contribution that follows the repository's development workflow.

For installation, first-run setup, and end-user workflows, refer to the
[Getting Started](getting-started.md) and [User Guide](user-guide.md) sections.

<!--hide_directive
:::{toctree}
:hidden:

Architecture <./developer-guide/architecture>
Performance Metrics <./developer-guide/metrics>
./developer-guide/contributing-guide

:::
hide_directive-->