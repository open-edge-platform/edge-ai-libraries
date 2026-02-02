# Visual Pipeline and Platform Evaluation Tool
<!-- required for catalog, do not remove -->
Assess Intel® hardware options, benchmark performance, and analyze key metrics to optimize hardware selection for AI workloads.

![Overview](docs/user-guide/_assets/ViPPET-README.gif)

<!--
**Guidelines for Authors**:
- Clearly explain the application’s purpose in one or two paragraphs.
- Describe the primary domain and high-level goal.
- Follow Microsoft Writing Guidelines: Use direct, active voice and avoid unnecessary jargon.
-->

## Overview

The Visual Pipeline and Platform Evaluation Tool simplifies hardware selection for AI workloads by enabling
configuration of workload parameters, performance benchmarking, and analysis of key metrics such as throughput,
CPU usage, and GPU usage. With its intuitive interface, the tool provides actionable insights that support
optimized hardware selection and performance tuning.

### Use Cases

<!--
**Guidelines for Authors**:
- Provide two or three real-world use cases in "Problem → Solution → Outcome" format.
- Ensure use cases are practical and highlight unique features of the application.
-->

**Evaluating Hardware for AI Workloads**: Intel® hardware options can be assessed to balance cost, performance,
and efficiency. AI workloads can be benchmarked under real-world conditions by adjusting pipeline parameters
and comparing performance metrics.

**Performance Benchmarking for AI Models**: Model performance targets and KPIs can be validated by testing AI
inference pipelines with different accelerators to measure throughput, latency, and resource utilization.

### Key Features

<!--
**Guidelines for Authors**:
- Clearly highlight value propositions.
- Use concise, benefit-driven statements.
-->

**Optimized for Intel® AI Edge Systems**: Pipelines can be run directly on target devices for seamless Intel®
hardware integration.

**Comprehensive Hardware Evaluation**: Metrics such as CPU frequency, GPU power usage, and memory utilization
are available for detailed analysis.

**Configurable AI Pipelines**: Parameters such as input channels, object detection models, and inference engines
can be adjusted to create tailored performance tests.

**Automated Video Generation**: Synthetic test videos can be generated to evaluate system performance under
controlled conditions.

### **Workflow Overview**

**Data Ingestion**: Video streams from live cameras or recorded files are provided and pipeline parameters are
configured to match evaluation needs.

**AI Processing**: AI inference is applied using OpenVINO™ models to detect objects in the video streams.

**Performance Evaluation**: Hardware performance metrics are collected, including CPU/GPU usage and power consumption.

**Visualization & Analysis**: Real-time performance metrics are displayed on the dashboard to enable comparison of
configurations and optimization of settings.

## Learn More

- [System Requirements](docs/user-guide/get-started/system-requirements.md)
- [Get Started](docs/user-guide/get-started.md)
- [How to Build Source](docs/user-guide/get-started/build-from-source.md)
- [How to Use ViPPET](docs/user-guide/use-vippet.md)
- [How to Use Video Generator](docs/user-guide/how-to-guides/use-video-generator.md)
- [Release Notes](docs/user-guide/release-notes.md)
