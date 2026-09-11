# Release Notes

## Current Release

**Version**: 1.0.0 \
**Release Date**: June 2026

**Features**:

- **Initial release** of the Agentic Predictive Maintenance blueprint.
- Config-driven multi-agent pipeline using LangGraph. Adapt to any defect detection use case by editing four configuration files — no code changes required.
- Four-agent reasoning pipeline: Policy Agent, Analysis Agent, Evidence Agent, and Ticketing Agent run sequentially to analyze detections and generate structured maintenance tickets.
- Two operating modes: LLM mode for AI-generated analysis (using `vlm-openvino-serving`) and fallback mode for rule-based operation without an LLM service.
- Real-time video inference via DL Streamer with YOLO-based object detection. Detection events published over MQTT.
- SQLite-backed storage service with REST API for querying detections and statistics.
- Web dashboard (React) with live detection feed, run history, and ticket viewer.
- Prometheus metrics exposed by both the storage service and agent service.
- Reference use case: `pipeline-defect-detection` with four defect classes — Rupture, Deformation, Disconnect, and Obstacle.
- Data preparation script for downloading and building sample video from a public Kaggle dataset.
- `AUTO_RUN_ON_DETECTION` support for automatic agent pipeline triggering after a configurable number of detections.

**Hardware Used for Validation**:

- Intel® Xeon® 5th Gen (CPU-only)
- Intel® Core™ Ultra with Intel® Arc™ GPU (LLM mode)

**Known Limitations**:

- NPU inference support for the LLM service is experimental and not validated for all model and configuration combinations.
- Only the `pipeline-defect-detection` use case is provided as a reference configuration. Additional use cases require manual configuration file setup.
- The Helm chart for Kubernetes deployment is not included in this release.
- GPU-specific sizing and performance benchmarks are not yet published.
