# ViPPET's Architecture

This section summarizes the core components ViPPET is built from. These components are grouped into
ViPPET application specific services, foundational services, which provide platform-wide capabilities,
and analytics services, which provide inference functionality.

![alt text](../../_assets/VIPPET-architecture-2026.1.svg "Title")

## Application Specific Microservices

Duis sunt ad aliqua et pariatur nostrud veniam nostrud tempor eiusmod.
Sit id minim eiusmod quis excepteur minim dolore. Labore Lorem nulla sint culpa.

| Microservice                                     | Description                                                                                                                                                                    | Docs                 | API        |
|--------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------|------------|
| ![alt text](../../_assets/ViPPET-UI.svg "Title") | **ViPPET UI** microservice provides the web-based React interface for user interaction. It integrates with backend and foundation services through secure API calls.           | [Docs](vippet-ui.md) | N/A        |
| ![alt text](../../_assets/ViPPET-BE.svg "Title") | **ViPPET BE (Backend)** microservice orchestrates workflows and exposes core application APIs. It manages user requests, coordinates jobs, and routes analytics results to UI. | [Docs](vippet-be.md) | <a>API</a> |
| ![alt text](../../_assets/ONVIF.svg "Title")     | **ViPPET ONVIF Discovery** TODO.                                                                                                                                               | <a>Docs</a>          | <a>API</a> |

## Middleware Microservices

Middleware microservices provide shared infrastructure capabilities reused across all Edge AI suites,
including stream ingestion, model lifecycle management, and operational observability.

| Microservice                                          | Description                                                                                                                                                                               | Docs        | API        |
|-------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------|------------|
| ![alt text](../../_assets/StreamManager.svg "Title")  | **Stream Manager** microservice ingests, manages, and distributes camera/video streams. It normalizes stream input for downstream analytics services and handles source lifecycle events. | <a>Docs</a> | <a>API</a> |
| ![alt text](../../_assets/ModelManager.svg "Title")   | **Model Manager** microservice centralizes model metadata, versions, and deployment targets. It exposes model lookup and routing interfaces used by training and inference pipelines.     | <a>Docs</a> | <a>API</a> |
| ![alt text](../../_assets/MetricsManager.svg "Title") | **Metrics Manager** microservice collects and aggregates runtime telemetry such as throughput, latency, health, and resource usage for observability and capacity planning.               | <a>Docs</a> | <a>API</a> |

## AI Analytics Microservices

AI Analytics microservices deliver domain-specific intelligence by executing machine learning models
against incoming data streams and returning structured results to the platform.

| Microservice                                           | Description                                                                                                                                                                                                     | Docs        | API        |
|--------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------|------------|
| ![alt text](../../_assets/VisionAnalytics.svg "Title") | **Vision Analytics** microservice runs optimized inference pipelines for vision workloads. It receives media frames, executes model inference, and returns detections/classifications for downstream consumers. | <a>Docs</a> | <a>API</a> |
| ![alt text](../../_assets/TSAnalytics.svg "Title")     | **Time-series Analytics** microservice provides flexible solution for real-time analysis of time series data.                                                                                                   | <a>Docs</a> | <a>API</a> |
| ![alt text](../../_assets/OVMS.svg "Title")            | **OpenVINO Model Server (OVMS)** serves optimized OpenVINO IR and ONNX models over gRPC and REST endpoints, enabling scalable, hardware-accelerated inference on CPU, GPU, and NPU targets.                     | <a>Docs</a> | <a>API</a> |
