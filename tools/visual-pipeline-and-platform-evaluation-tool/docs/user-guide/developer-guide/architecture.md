# ViPPET's Architecture

This section summarizes the core components ViPPET is built from. These components are grouped into
ViPPET application specific services and foundational services, which provide platform-wide capabilities.

![alt text](../_assets/VIPPET-architecture-2026.1.svg "Title")

## Application Specific Microservices

Application-specific microservices implement ViPPET's end-user workflows. Together they provide the
web UI, the backend control plane for pipelines and jobs, and the network camera discovery path used
to onboard ONVIF-compatible devices.

| Microservice                                  | Description                                                                                                                                                                    | Docs                                | API        |
|-----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------|------------|
| ![alt text](../_assets/ViPPET-UI.svg "Title") | **ViPPET UI** microservice provides the web-based React interface for user interaction. It integrates with backend and foundation services through secure API calls.           | [Docs](./architecture/vippet-ui.md) | N/A        |
| ![alt text](../_assets/ViPPET-BE.svg "Title") | **ViPPET BE (Backend)** microservice orchestrates workflows and exposes core application APIs. It manages user requests, coordinates jobs, and routes analytics results to UI. | [Docs](./architecture/vippet-be.md) | <a>API</a> |
| ![alt text](../_assets/ONVIF.svg "Title")     | **ViPPET ONVIF Discovery** microservice is used to discover ONVIF-capable network cameras on the local subnet.                                                                 | N/A                                 | N/A        |

## Middleware Microservices

Middleware microservices provide shared infrastructure capabilities reused across all Edge AI suites,
including stream ingestion, model lifecycle management, and operational observability.

| Microservice                                       | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Docs                                                                                             | API                                                                                                     |
|----------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| ![alt text](../_assets/ModelManager.svg "Title")   | **Model Download** microservice is a centralized model management system that downloads AI or machine learning models from various model hubs while ensuring consistency and simplicity across applications, stores the models, accepts custom model uploads, and handles optional format conversions.                                                                                                                                                                                                 | [Docs](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/index.html)  | [API](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/api-reference.html)  |
| ![alt text](../_assets/MetricsManager.svg "Title") | **Metrics Manager** service for unified collection, ingestion, and real-time relay of system and application metrics on edge and cloud nodes. It bundles Telegraf-based hardware telemetry (CPU, memory, temperature, Intel® GPU, Intel® NPU) with a FastAPI REST surface that accepts custom metrics in JSON, InfluxDB Line Protocol, and OpenTelemetry formats, and exposes them through a Prometheus-compatible endpoint as well as a Server-Sent Events (SSE) stream suitable for live dashboards. | [Docs](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/metrics-manager/index.html) | [API](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/metrics-manager/api-reference.html) |

<!--hide_directive
:::{toctree}
:hidden:

VIPPET UI <./architecture/vippet-ui>
VIPPET Backend <./architecture/vippet-be>

:::
hide_directive-->