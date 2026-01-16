Visual Pipeline and Platform Evaluation Tool
============================================

Assess Intel® hardware options, benchmark performance, and analyze key metrics to optimize hardware selection for AI workloads.

Overview
########

The Visual Pipeline and Platform Evaluation Tool simplifies hardware selection for AI workloads by enabling configuration of workload parameters, performance benchmarking, and analysis of key metrics such as throughput, CPU usage, and GPU usage. With its intuitive interface, the tool provides actionable insights that support optimized hardware selection and performance tuning.

Use Cases
#########

**Evaluating Hardware for AI Workloads**: Intel® hardware options can be assessed to balance cost, performance, and efficiency. AI workloads can be benchmarked under real-world conditions by adjusting pipeline parameters and comparing performance metrics.

**Performance Benchmarking for AI Models**: Model performance targets and KPIs can be validated by testing AI inference pipelines with different accelerators to measure throughput, latency, and resource utilization.

Key Features
############

**Optimized for Intel® AI Edge Systems**: Pipelines can be run directly on target devices for seamless Intel® hardware integration.

**Comprehensive Hardware Evaluation**: Metrics such as CPU frequency, GPU power usage, and memory utilization are available for detailed analysis.

**Configurable AI Pipelines**: Parameters such as input channels, object detection models, and inference engines can be adjusted to create tailored performance tests.

**Automated Video Generation**: Synthetic test videos can be generated to evaluate system performance under controlled conditions.

How It Works
############

The Visual Pipeline and Platform Evaluation Tool integrates with AI-based video processing pipelines to support hardware performance evaluation.

.. image:: ./_assets/architecture.png
   :alt: System Architecture Diagram

### **Workflow Overview**

**Data Ingestion**: Video streams from live cameras or recorded files are provided and pipeline parameters are configured to match evaluation needs.

**AI Processing**: AI inference is applied using OpenVINO™ models to detect objects in the video streams.

**Performance Evaluation**: Hardware performance metrics are collected, including CPU/GPU usage and power consumption.

**Visualization & Analysis**: Real-time performance metrics are displayed on the dashboard to enable comparison of configurations and optimization of settings.

Learn More
##########

- :doc:`System Requirements <./system-requirements>`
- :doc:`Get Started <./get-started>`
- :doc:`How to Build Source <./how-to-build-source>`
- :doc:`How to use Video Generator <./how-to-use-video-generator>`
- :doc:`Release Notes <./release-notes>`

.. toctree::
   :hidden:
   :maxdepth: 2

   system-requirements
   get-started
   release-notes
   how-to-build-source
   how-to-use-video-generator
   api-reference
   disclaimers
   known-issues
   GitHub <https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool>
