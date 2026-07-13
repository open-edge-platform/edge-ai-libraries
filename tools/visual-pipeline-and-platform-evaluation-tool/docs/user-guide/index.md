# Visual Pipeline and Platform Evaluation Tool

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/tools/visual-pipeline-and-platform-evaluation-tool">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/tools/visual-pipeline-and-platform-evaluation-tool/README.md">
     Readme
  </a>
</div>
hide_directive-->

## What is ViPPET

The Visual Pipeline and Platform Evaluation Tool simplifies hardware selection for AI workloads by enabling
configuration of workload parameters, performance benchmarking, and analysis of key metrics such as
throughput, CPU usage, and GPU usage. With its intuitive interface, the tool provides actionable insights that
support optimized hardware selection and performance tuning.

ViPPET helps you compare how AI pipelines behave across hardware targets, model variants, and input sources so you
can make better deployment decisions earlier in the development cycle.

## Common Use Cases

**Evaluating Hardware for AI Workloads**: Intel® hardware options can be assessed to balance
cost, performance, and efficiency. AI workloads can be benchmarked under real-world conditions
by adjusting pipeline parameters and comparing performance metrics.

**Performance Benchmarking for AI Models**: Model performance targets and KPIs can be validated
by testing AI inference pipelines with different accelerators to measure throughput, latency,
and resource utilization.

**Validating End-to-End Pipelines**: Complete media and AI pipelines can be exercised with different
inputs, models, and execution settings to understand real deployment behavior instead of relying on
component-level measurements alone.

## Key Features

**Optimized for Intel® AI Edge Systems**:
Pipelines can be run directly on target devices for
seamless Intel® hardware integration.

**Comprehensive Hardware Evaluation**: Metrics such as CPU frequency, GPU power usage, and
memory utilization are available for detailed analysis.

**Predefined and Custom Pipelines**: ViPPET includes ready-to-use pipeline templates and also allows
you to configure custom inputs, models, and execution paths for your own evaluation scenarios.

**Built-In Performance Visibility**: Throughput, latency, and system utilization metrics are collected
in one place, making it easier to identify bottlenecks and compare platform behavior.

## Resources

- [Get Started](./get-started.md)
- [User Guide](./user-guide.md)
- [Developer Guide](./developer-guide.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started
./user-guide
./developer-guide
./troubleshooting
Release Notes <./release-notes.md>

:::
hide_directive-->