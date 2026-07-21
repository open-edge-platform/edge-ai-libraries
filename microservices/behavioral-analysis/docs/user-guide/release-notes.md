# Release Notes

## Version 1.0.0

**Release date:** 2026

**Source:** `pyproject.toml` — `version = "1.0.0"`; `main.py` — `version="1.0.0"`; copyright headers — `(C) 2026 Intel Corporation`.

### Summary

Initial release of the Behavioral Analysis Service — a pose-based suspicious activity detection microservice for retail loss-prevention use cases.

### Features

- YOLO26n-pose inference via OpenVINO Runtime (no PyTorch dependency)
- Declarative YAML behavioral pattern engine — add new patterns without code changes
- Built-in `shelf_to_waist` concealment detection pattern
- Optional VLM confirmation via OpenVINO Model Server (Qwen2.5-VL-7B-Instruct)
- Event-driven MQTT processing: `ba/requests` → `ba/results`
- Async SeaweedFS (S3-compatible) frame retrieval via `aioboto3`
- Circuit breaker in VLM client (3-failure threshold, 30-second cooldown)
- Entity deduplication and max-concurrency backpressure in the MQTT consumer
- Base image: `intel/dlstreamer:2026.1.0-ubuntu24` (Python 3.12)

### Dependency Versions (from `requirements.txt` and `pyproject.toml`)

| Package | Version Constraint |
|---|---|
| `fastapi` | `>=0.109.0` |
| `uvicorn[standard]` | `>=0.27.0` |
| `pydantic` | `>=2.5.0` |
| `pydantic-settings` | `>=2.1.0` |
| `opencv-python-headless` | `>=4.9.0` |
| `Pillow` | `>=10.0` |
| `aioboto3` | `>=12.0.0` |
| `httpx` | `>=0.26.0` |
| `h2` | `>=4.0` |
| `pyyaml` | `>=6.0` |
| `paho-mqtt` | `>=1.6.1,<2.0` |
| Base image OpenVINO | Provided by `intel/dlstreamer:2026.1.0-ubuntu24` |
