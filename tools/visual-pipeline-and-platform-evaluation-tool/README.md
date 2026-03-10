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

### Performance Testing Capabilities

**Single Pipeline Testing**:
Test individual AI pipelines with configurable stream counts to measure baseline performance.
Users can specify the number of concurrent streams and optionally save output videos for quality verification.
Real-time metrics including Total FPS and Per Stream FPS are displayed during testing.

**Multi-Pipeline Concurrent Testing**:
Evaluate system performance under complex workloads by running multiple different pipelines simultaneously.
Each pipeline can be configured with its own stream count, allowing simulation of real-world deployment scenarios
where multiple AI workloads compete for system resources.

**Real-Time Metrics Dashboard**:
Monitor CPU frequency, GPU power usage, memory utilization, and throughput metrics in real-time during all
performance tests.
This enables immediate identification of bottlenecks and resource constraints.

**Output Video Validation**:
Optionally capture and save processed video outputs during performance testing to verify
that AI inference quality is maintained under load conditions.

### Density Testing

**Automated Stream Density Discovery**:
Determine the maximum number of concurrent streams your hardware can sustain while maintaining a minimum FPS
threshold.
The density test automatically scales up stream counts until performance drops below the specified `fps_floor`,
providing precise hardware capacity measurements.

**Multi-Pipeline Density Analysis**:
Test complex workload scenarios by running multiple different pipelines simultaneously with configurable stream
rate ratios.
For example, allocate 70% of streams to object detection and 30% to license plate recognition to simulate
real-world deployment conditions.

**FPS Floor Validation**:
Set minimum acceptable performance thresholds (for example, 30 FPS per stream)
and automatically discover the maximum sustainable workload.
This eliminates guesswork in capacity planning and ensures deployments meet performance requirements.

**Capacity Planning Support**:
Generate precise hardware sizing recommendations by measuring actual stream density under controlled conditions.
Results show exactly how many concurrent video streams each hardware configuration can process
while maintaining quality thresholds.

### **Workflow Overview**

**Data Ingestion**: Video streams from live cameras or recorded files are provided and pipeline parameters are
configured to match evaluation needs.

**AI Processing**: AI inference is applied using OpenVINO™ models to detect objects in the video streams.

**Performance Evaluation**: Hardware performance metrics are collected, including CPU/GPU usage and power consumption.

**Visualization & Analysis**: Real-time performance metrics are displayed on the dashboard to enable comparison of
configurations and optimization of settings.

## Example: Real-Time License Plate Recognition (ALPR)

This use case mirrors a common smart city workload and can be reproduced in ViPPET to compare Intel® platforms for
license plate analytics.

**Goal**: Detect vehicles, localize license plates, and read plate text from live or recorded video in real time.

For the complete architecture, hardware variants (CPU/GPU/GPU+NPU), pipeline examples, and benchmark guidance, see:

- [License Plate Recognition Pipeline Guide](docs/user-guide/how-to-guides/license-plate-recognition-pipeline.md)

Use ViPPET's built-in **Performance Test** and **Density Test** to collect measured platform-specific throughput,
latency, utilization, and sustainable stream density.

## Learn More

- [System Requirements](docs/user-guide/get-started/system-requirements.md)
- [Get Started](docs/user-guide/get-started.md)
- [How to Build Source](docs/user-guide/get-started/build-from-source.md)
- [How to Use ViPPET](docs/user-guide/use-vippet.md)
- [How to Build License Plate Recognition Pipeline](docs/user-guide/how-to-guides/license-plate-recognition-pipeline.md)
- [How to Run Performance Tests](docs/user-guide/how-to-guides/performance-testing.md)
- [How to Run Density Tests](docs/user-guide/how-to-guides/density-testing.md)
- [How to Use Video Generator](docs/user-guide/how-to-guides/use-video-generator.md)
- [Release Notes](docs/user-guide/release-notes.md)

## Contribution Rules

- Follow repository-wide Copilot guidance in [.github/copilot-instructions.md](.github/copilot-instructions.md).
- Keep pull requests focused and avoid unrelated refactors.
- Run `make lint` before opening or updating a PR.
- Run `make test` (or targeted tests) for changed code paths.
- Update docs and API artifacts when behavior or endpoints change.
