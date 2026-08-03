# Working with other services

DL Streamer Pipeline Server can work with following microservices for visualization and model management.

## Model Download

The [Model Download microservice](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/index.html) provides a REST API to download AI/ML models from multiple hubs (Hugging Face, Ultralytics, Ollama, Geti™ software, and Pipeline Zoo Models) and optionally convert them to OpenVINO™ IR format. By mounting a shared volume between Model Download and DL Streamer Pipeline Server, downloaded models become immediately accessible to DLSPS pipelines without any manual file transfer.

### Architecture Overview

Both services share a host directory mounted as a volume:

- **Model Download** writes models to `/opt/models` inside its container.
- **DL Streamer Pipeline Server** reads models from `/home/pipeline-server/models` inside its container.
- Both paths are mapped to the **same host directory**, so models downloaded through the Model Download API are instantly available to DLSPS.

### Setup with Docker Compose

Add both services to a Docker Compose file and declare a shared named volume (or bind-mount a host path):

```yaml
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

services:
  model-download:
    image: intel/model-download:latest
    container_name: model-download
    command: --plugins all
    ports:
      - "8200:8000"
    environment:
      - MODEL_PATH=/opt/models
      - HF_TOKEN=${HUGGINGFACEHUB_API_TOKEN:-}
    volumes:
      - shared_models:/opt/models
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s

  dlstreamer-pipeline-server:
    image: ${DLSTREAMER_PIPELINE_SERVER_IMAGE}
    container_name: dlstreamer-pipeline-server
    ports:
      - "8080:8080"
    volumes:
      - shared_models:/home/pipeline-server/models:ro
      # ... other required DLSPS volume mounts
    depends_on:
      model-download:
        condition: service_healthy

volumes:
  shared_models:
```

> **Note:** The `shared_models` named volume ensures both containers operate on the same model files. The `:ro` flag on the DLSPS side is optional but recommended to prevent DLSPS from accidentally modifying downloaded models.

### Downloading Models via the Model Download API

Once the services are running, use the Model Download REST API to pull models onto the shared volume. DLSPS can then reference them directly in pipeline configurations.

**Step 1 – Start the services:**

```bash
docker compose up -d
```

**Step 2 – Request a model download** (example: YOLOv8 from Ultralytics):

```bash
curl -X POST "http://localhost:8200/api/v1/models/download?download_path=yolo_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8s",
        "hub": "ultralytics",
        "type": "vision"
      }
    ],
    "parallel_downloads": false
  }'
```

The response contains a `job_id`:

```json
{
  "message": "Started processing 1 model(s)",
  "job_ids": ["5f0d4eba-c79c-4d02-97a6-43c3d0168ca0"],
  "status": "processing"
}
```

**Step 3 – Poll for completion** before launching pipelines:

```bash
curl -X GET "http://localhost:8200/api/v1/jobs/5f0d4eba-c79c-4d02-97a6-43c3d0168ca0"
```

Wait until the response shows `"status": "completed"`. The `result.download_path` field indicates the subdirectory under the shared volume where the model files were saved.

**Step 4 – Reference the model in a DLSPS pipeline** using the path inside the DLSPS container (`/home/pipeline-server/models/<download_path>`).

### Additional Resources

- [Model Download Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/index.html)
- [Model Download API Reference](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-download/index.html) – full OpenAPI spec including upload, conversion, and job management endpoints