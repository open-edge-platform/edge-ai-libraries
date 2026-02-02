# How It Works

The Visual Pipeline and Platform Evaluation Tool integrates with AI-based video processing
pipelines to support hardware performance evaluation.

![System Architecture Diagram](./_assets/architecture.png)

## Workflow

**Data Ingestion**: Video streams from live cameras or recorded files are provided and pipeline
parameters are configured to match evaluation needs.

**AI Processing**: AI inference is applied using OpenVINO™ models to detect objects in the
video streams.

**Performance Evaluation**: Hardware performance metrics are collected, including CPU/GPU usage
and power consumption.

**Visualization & Analysis**: Real-time performance metrics are displayed on the dashboard to
enable comparison of configurations and optimization of settings.
