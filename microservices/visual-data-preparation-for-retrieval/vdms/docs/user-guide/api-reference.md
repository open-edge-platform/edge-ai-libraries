# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: api-docs/openapi.yaml
```hide_directive-->

The Visual Data Preparation for Retrieval (VDMS DataPrep) microservice exposes REST APIs for
video ingestion, frame/object embedding generation, telemetry retrieval, and MinIO-backed video
management.

The repository OpenAPI spec is available at [`api-docs/openapi.yaml`](./api-docs/openapi.yaml).

## Interactive API Documentation

When the service is running, FastAPI provides interactive docs:

- **Swagger UI**: `http://<HOST_IP>:<VDMS_DATAPREP_HOST_PORT>/docs`
- **ReDoc**: `http://<HOST_IP>:<VDMS_DATAPREP_HOST_PORT>/redoc`
- **OpenAPI JSON**: `http://<HOST_IP>:<VDMS_DATAPREP_HOST_PORT>/openapi.json`

With default settings:

```bash
http://<HOST_IP>:6007/docs
http://<HOST_IP>:6007/redoc
http://<HOST_IP>:6007/openapi.json
```

## API Overview

| Category | Endpoint | Description |
| -------- | -------- | ----------- |
| **Service** | `GET /health` | Returns service readiness and SDK preload status |
| **Document Processing** | `POST /summary` | Creates embedding entries from text summary + timestamp metadata |
| **Video Processing** | `POST /videos/upload` | Uploads MP4 to MinIO and generates frame/object embeddings |
| **Video Processing** | `POST /videos/minio` | Processes an existing MinIO video and generates embeddings |
| **Video Processing** | `POST /videos/rtsp` | Processes RTSP stream URLs for frame/object embeddings |
| **Telemetry** | `GET /telemetry` | Returns recent runtime telemetry records |
| **Video Management** | `GET /videos` | Lists processed videos in a bucket |
| **Video Management** | `GET /videos/download` | Streams or downloads a stored MP4 from MinIO |
| **Video Management** | `DELETE /videos/{bucket_name}/{video_id}` | Deletes one video or an entire video directory |

## Using the OpenAPI Spec with Bruno

For collection generation and API testing, import the checked-in spec:

- File: `docs/user-guide/api-docs/openapi.yaml`
- Bruno: **Collections → Import OpenAPI** and select this YAML file

This file is generated from the FastAPI app and is the recommended source for reproducible Bruno collections.
