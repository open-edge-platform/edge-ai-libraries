# Visual Pipeline and Platform Evaluation Tool
<!-- required for catalog, do not remove -->
Assess Intel® hardware options, benchmark performance, and analyze key metrics to optimize hardware selection for AI workloads.

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

## Experimental Time Series setup

The tool also includes an experimental Time Series deployment for testing pipeline variants that are separate from the
standard application stack. This setup is managed through the Makefile targets shown below:

```make
build-experimental: env-setup ## Build core images for experimental timeseries setup

run-experimental: env-setup ## Run the docker compose services with experimental timeseries features

stop-experimental: ## Stop experimental docker compose services

clean-experimental: ## Clean experimental setup artifacts
```

Use this flow when you want to build and start the experimental Time Series environment without affecting the main
compose stack:

1. Build the experimental images with `make build-experimental`.
2. Start the services with `make run-experimental`.
3. Stop them with `make stop-experimental` when testing is complete.
4. Remove the generated containers and volumes with `make clean-experimental`.

This keeps the experimental Time Series pipeline isolated behind the separate `compose-experimental.yml` definition,
while still reusing the same hardware-specific profile selection from `setup_env.sh` and `.env`.

## Learn More

The following resources provide comprehensive guidance on installation, usage, and development of the Visual
Pipeline and Platform Evaluation Tool:

- [System Requirements](./docs/user-guide/get-started/installation/system-requirements.md)
- [Installation](./docs/user-guide/get-started/installation.md)
- [Quickstart Guide](./docs/user-guide/get-started/quickstart.md)
- [Input Management](./docs/user-guide/user-guide/input-management.md)
- [Architecture](./docs/user-guide/developer-guide/architecture.md)
- [Troubleshooting](./docs/user-guide/troubleshooting.md)
- [Release Notes](./docs/user-guide/release-notes.md)

## Contribution Rules

- Follow repository-wide Copilot guidance in [.github/copilot-instructions.md](.github/copilot-instructions.md).
- Keep pull requests focused and avoid unrelated refactors.
- Run `make lint` before opening or updating a PR.
- Run `make test` (or targeted tests) for changed code paths.
- Update docs and API artifacts when behavior or endpoints change.
