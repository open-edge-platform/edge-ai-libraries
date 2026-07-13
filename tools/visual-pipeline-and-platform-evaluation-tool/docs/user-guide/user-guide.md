# User Guide

Use this guide to learn how to work with ViPPET after the platform is installed and running.
It introduces the main workflows used in day-to-day evaluation work: preparing inputs, managing models,
building pipelines, running benchmarks, and improving performance on Intel® hardware.

If you are new to ViPPET, complete the [Get Started](./get-started.md) section first.
Then use this guide to move from basic setup to practical pipeline execution and optimization.

## What this guide covers

The User Guide is organized around the main tasks you perform in the ViPPET UI:

**Preparing inputs**: Learn how to work with live cameras, uploaded image sets, and video files in the
[Input Management](./user-guide/input-management.md) section.

**Managing models**: Learn how to install supported models, upload your own OpenVINO™ models, and prepare
them for use in pipelines in the [Model Management](./user-guide/model-management.md) section.

**Working with pipelines**: Learn how to create, configure, and run pipelines, choose between simple and
advanced views, and use predefined templates in the [Working With Pipelines](./user-guide/pipeline-management.md) section.

**Benchmarking platform behavior**: Learn how to measure throughput, compare pipeline performance, and find
maximum stream density in the [Benchmarking](./user-guide/benchmarking.md) section.

<!-- Input in progress: **Improving performance**: Learn how to tune inference, decode and encode settings, profile workloads,
and choose the right execution strategy in the [Performance Optimization](./user-guide/performance-optimization.md) section.-->

## Recommended path

If you are using ViPPET for the first time, this sequence works well:

1. Start with [Input Management](./user-guide/input-management.md) to prepare the data sources you want to test.
2. Continue with [Model Management](./user-guide/model-management.md) to install or upload the models your pipelines need.
3. Move to [Working With Pipelines](./user-guide/pipeline-management.md) to assemble and run end-to-end workloads.
4. Use [Benchmarking](./user-guide/benchmarking.md) to collect FPS, utilization, and other execution results.

<!-- Input in progress: 5. Finish with [Performance Optimization](./user-guide/performance-optimization.md)
to tune the pipeline and hardware configuration. -->

## When to use this guide

Use the User Guide when you want to:

- set up inputs and models for a practical evaluation workflow,
- configure and execute AI pipelines in the ViPPET UI,
- compare pipeline behavior across different devices or stream counts,
- understand where performance bottlenecks appear,
- apply tuning techniques before moving to more advanced platform or architecture topics.

For system architecture, integrations, and contribution workflows, continue to the
[Developer Guide](./developer-guide.md).

<!--hide_directive
:::{toctree}
:hidden:

./user-guide/input-management
./user-guide/model-management
./user-guide/pipeline-management
./user-guide/benchmarking

:::
hide_directive-->
