# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: _assets/vss-api.yaml
```hide_directive-->

The Video Search and Summarization application exposes REST APIs through several microservices. The full OpenAPI specification for the Pipeline Manager is available in [`_assets/vss-api.yaml`](_assets/vss-api.yaml).

## Interactive API Documentation

Each service listed below auto-generates an interactive API explorer (powered by [Swagger UI](https://swagger.io/tools/swagger-ui/) via FastAPI / NestJS) where you can browse endpoints, inspect request/response schemas, and execute live requests directly from the browser using **Try it out**.

> **Prerequisite:** The application must be running (via `source setup.sh --summary`, `--search`, `--dual`, or `--unified`).

| Service | URL | Availability |
| ------- | --- | ------------ |
| **Pipeline Manager** | `http://<HOST_IP>:<APP_HOST_PORT>/manager/docs` | All modes |
| **Data Prep** | `http://<HOST_IP>:<VS_HOST_PORT>/docs` | `--search`, `--dual`, `--unified` |
| **Multimodal Embedding Serving** | `http://<HOST_IP>:<EMBEDDING_SERVER_PORT>/docs` | `--search`, `--dual`, `--unified` |

With default ports, the URLs are:

```bash
# Pipeline Manager — video upload, search, summarization, health, config
http://<HOST_IP>:12345/manager/docs

# Data Prep — data ingestion and frame processing
http://<HOST_IP>:7890/docs

# Multimodal Embedding Serving — embedding generation
http://<HOST_IP>:9777/docs
```

Replace `<HOST_IP>` with the IP address or hostname of the machine running the application.

## Pipeline Manager API Overview

The Pipeline Manager is the primary API for interacting with the application. Its endpoints are organized into the following groups:

| Category | Endpoints | Description |
| -------- | --------- | ----------- |
| **Health** | `GET /health` | Service health status |
| **App** | `GET /app/config`, `GET /app/features` | System configuration and feature flags |
| **Pipeline** | `GET /pipeline/frames`, `GET /pipeline/evam` | Frame and EVAM pipeline status |
| **Metrics** | `GET /metrics/status` | Telemetry collector connection status |
| **Audio** | `GET /audio/models` | Available audio transcription models |
| **Tags** | `GET /tags`, `DELETE /tags/{tagId}` | Tag management |
| **Video** | `POST /videos`, `GET /videos`, `GET /videos/{videoId}`, `POST /videos/search-embeddings/{videoId}` | Video upload, listing, and embedding creation |
| **Search** | `POST /search`, `GET /search`, `POST /search/query`, `GET /search/{queryId}`, `DELETE /search/{queryId}`, `POST /search/{queryId}/refetch`, `PATCH /search/{queryId}/watch`, `GET /search/watched` | Search query management and execution |
| **Summary** | `POST /summary`, `GET /summary`, `GET /summary/ui`, `GET /summary/{stateId}`, `GET /summary/{stateId}/raw`, `DELETE /summary/{stateId}` | Video summarization pipeline |

> **Note:** When accessing the Pipeline Manager through nginx, all paths are prefixed with `/manager/` (for example, `GET /manager/health`).

For full request/response schemas, refer to the interactive docs or the OpenAPI spec.

## Using the OpenAPI Specification Offline

The Pipeline Manager OpenAPI spec is available in two ways:

**From the repository:**

The file [`docs/user-guide/_assets/vss-api.yaml`](_assets/vss-api.yaml) can be loaded into any OpenAPI-compatible tool:

- [Swagger Editor](https://editor.swagger.io/) — paste or import the YAML to browse and try endpoints
- [Bruno](https://www.usebruno.com/) — import the YAML file to generate a ready-to-use request collection

**From a running instance:**

The Pipeline Manager also serves its spec at runtime:

```bash
# JSON format
curl http://<HOST_IP>:<APP_HOST_PORT>/manager/swagger/json

# YAML format
curl http://<HOST_IP>:<APP_HOST_PORT>/manager/swagger/yaml
```
