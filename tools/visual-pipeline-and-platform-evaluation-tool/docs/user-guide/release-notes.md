# Release Notes: Visual Pipeline and Platform Evaluation Tool

Details about the changes, improvements, and known issues in this release of the application.

## Release 2026.3

- Uses DL Streamer Pipeline Server 2.0 as the execution engine for ViPPET pipelines,
  tests, and benchmarks.
- Added face recognition, alerting, CV-triggered VLM  and Media Decode pipeline capabilities.
- Added Speech to Text and Text to Speech audio pipelines.
- Moved camera discovery and management to the new Sensor Manager microservice,
  including GigE Vision support.
- Improved Model Management with category-based tables, direct Hugging Face, Ultralytics,
  and Geti 3.0 model discovery, and one-step installation of pipeline-required models.
- Added advanced-mode CPU core pinning to restrict pipeline execution to selected logical CPU cores.
- Enhanced benchmark and performance-test reporting with latency metrics, charts, HTML reports,
  and replayable configurations.
- Added the ViPPET Portal proof of concept for comparing results and running experiments
  across multiple ViPPET instances.

For a detailed listing of all the changes, see the
[Release notes for ViPPET 2026.3](./release-notes/release-2026.3.md).

## Release 2026.2

- New pipelines for showcasing DeepSORT tracking and (experimental) time-series anomaly detection
- Streamlined benchmarking and reporting for predefined workloads sets
- Added performance testing alongside functional tests
- Added support for InternVL2 & MiniCPM VLM and YOLO11/YOLO26 models
- Added proof-of-concept support for GigE/GenICam-compliant machine vision cameras
- Added option to find maximum stream density by fixing pipeline #1 count and
  incrementally testing pipeline #2 capacity
- Added documentation to make it easier to decide when to use ViPPET and Edge AI Sizing Tool

For a detailed listing of all the changes, see the
[Release notes for ViPPET 2026.2](./release-notes/release-2026.2.md).

## Release 2026.1

- New predefined pipelines for video summarization, motion detection, instance
  segmentation, and pose estimation.
- End-to-end pipeline latency reporting.
- NPU utilization metrics.
- Support for uploading custom video files.
- Support for uploading custom image sets.
- Support for uploading custom OpenVINO models, including Intel Geti-trained models.
- New microservices for model management and metrics collection.

For a detailed listing of all the changes, see the
[Release notes for ViPPET 2026.1](./release-notes/release-2026.1.md).

## Release 2026.0

- Demo mode tailored for events and demonstrations.
- Support for multiple pipeline variants (CPU, GPU, NPU).
- Ready-to-use optimized pipeline templates.
- Simplified pipeline view and improved editor layout.
- New predefined pipelines for retail, manufacturing, and metro scenarios.
- Automatic detection of USB and network cameras as inputs.
- Live WebRTC-based preview of pipeline output.
- Timed pipeline execution with automatic looping.
- Redesigned metrics charts with up to eight system indicators.
- Refreshed UI with updated navigation.

For a detailed listing of all the changes, see the
[Release notes for ViPPET 2026.0](./release-notes/release-2026.0.md).

## Release 2025.2

- New graphical pipeline editor.
- Pipeline import and export capabilities.
- Clear separation between backend and frontend services.
- Extensible architecture for dynamic pipeline registration.
- Integrated POSE model support.
- DL Streamer Optimizer integration for simpler configuration.
- Improved out-of-box performance tuning.
- Model management enhancements to add/remove supported models in-app.

For a detailed listing of all the changes, see the
[Release notes for ViPPET 2025.2](./release-notes/release-2025.2.md).

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2026.3 <./release-notes/release-2026.3.md>
Release Notes 2026.2 <./release-notes/release-2026.2.md>
Release Notes 2026.1 <./release-notes/release-2026.1.md>
Release Notes 2026.0 <./release-notes/release-2026.0.md>
Release Notes 2025.2 <./release-notes/release-2025.2.md>

:::
hide_directive-->
