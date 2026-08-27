# Release Notes

## Version 1.0.0

**Release date:** September 9, 2026

**Summary:**

Initial release of the Behavioral Analysis Service, a pose-based suspicious activity
detection microservice for retail loss-prevention use cases. This is a production-ready
microservice that leverages OpenVINO Runtime for efficient edge inference without
requiring PyTorch dependencies.

The Behavioral Analysis Service analyzes video frame sequences to detect suspicious behaviors by:

1. Extracting skeletal pose keypoints using YOLO26n-pose optimized with OpenVINO Runtime.
2. Evaluating pose sequences against behavioral patterns defined in YAML.
3. Optionally forwarding key frames to a Visual Language Model (VLM) for visual verification.

**Features:**

- **Pose extraction** — YOLO26n-pose inference via OpenVINO Runtime (no PyTorch dependency)
- **Declarative YAML behavioral pattern engine** — add new patterns without code changes
- **Built-in `shelf_to_waist` concealment detection pattern** — targeting retail shrinkage scenarios
- **Optional VLM confirmation** — via OpenVINO Model Server (Qwen2.5-VL-7B-Instruct)
- **Event-driven MQTT processing** — `ba/requests` → `ba/results` with entity deduplication
- **Async SeaweedFS (S3-compatible) frame retrieval** — via `aioboto3`
- **Circuit breaker in VLM client** — 3-failure threshold, 30-second cooldown
- **Entity deduplication and max-concurrency backpressure** — in the MQTT consumer
- **Base image** — `intel/dlstreamer:2026.2.0-ubuntu24` (Python 3.12)
- **Container-ready** — fully configurable via environment variables and volume-mounted YAML

**Use Cases:**

- **Retail loss prevention** — detect suspicious concealment behaviors (e.g., shelf-to-waist movements) in real time
- **Behavioral analysis at the edge** — extract and evaluate pose sequences without reliance on cloud inference
- **Multimodal detection** — combine pose-based detection with optional VLM visual verification for improved accuracy
- **Video surveillance** — efficient frame-by-frame behavioral monitoring in retail environments

**Known Limitations:**

- The service requires a reachable SceneScape deployment (MQTT broker + SeaweedFS) to produce meaningful output
- VLM confirmation adds latency; consider circuit breaker settings for high-throughput scenarios
- YOLO26n-pose inference performance is hardware-dependent; refer to System Requirements for supported compute devices
- Pattern definitions are YAML-based and require validation before deployment
