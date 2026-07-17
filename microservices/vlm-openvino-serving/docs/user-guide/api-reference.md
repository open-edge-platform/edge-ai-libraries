# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: api-docs/openapi.yaml
```hide_directive-->

The VLM OpenVINO Serving microservice exposes OpenAI-compatible chat completion APIs for multimodal prompts (text, images, and video), plus service, model, device, and telemetry APIs.
The repository OpenAPI spec is available at [`api-docs/openapi.yaml`](./api-docs/openapi.yaml).

## Interactive API Documentation

When the service is running, FastAPI provides interactive docs:

- **Swagger UI**: `http://<HOST_IP>:<VLM_SERVICE_PORT>/docs`
- **ReDoc**: `http://<HOST_IP>:<VLM_SERVICE_PORT>/redoc`
- **OpenAPI JSON**: `http://<HOST_IP>:<VLM_SERVICE_PORT>/openapi.json`

With default settings:

```bash
http://<HOST_IP>:9764/docs
http://<HOST_IP>:9764/redoc
http://<HOST_IP>:9764/openapi.json
```

## API Overview

| Category | Endpoint | Description |
| -------- | -------- | ----------- |
| **Service** | `GET /health` | Returns service readiness (`healthy` or `model not ready`) |
| **Service** | `GET /v1/queue-status` | Returns active and queued request counts |
| **Chat Completions** | `POST /v1/chat/completions` | Generates multimodal chat completions (JSON or SSE streaming) |
| **Telemetry** | `GET /v1/telemetry` | Returns newest telemetry records for recent chat requests |
| **Models** | `GET /v1/models` | Returns the model configured by this running server |
| **Device** | `GET /device` | Lists available OpenVINO devices on the host |
| **Device** | `GET /device/{device}` | Returns properties for a selected OpenVINO device |

## `/v1/chat/completions` Request Shape

`POST /v1/chat/completions` expects:

- `model`: configured model name (for example, `Qwen/Qwen2.5-VL-3B-Instruct`)
- `messages`: list of chat messages
  - `content` supports `text`, `image_url`, `video`, and `video_url` payloads
- generation parameters such as:
  - `max_completion_tokens`
  - `temperature`
  - `top_p`
  - `top_k`
  - `repetition_penalty`
  - `presence_penalty`
  - `frequency_penalty`
  - `seed`
  - `stream`

When `stream=false` (default), the endpoint returns a JSON response.
When `stream=true`, the endpoint returns `text/event-stream` chunks.

Example:

```bash
curl --location 'http://<HOST_IP>:9764/v1/chat/completions' \
  --header 'Content-Type: application/json' \
  --data '{
    "model": "Qwen/Qwen2.5-VL-3B-Instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "Describe this image."},
          {
            "type": "image_url",
            "image_url": {
              "url": "https://github.com/openvinotoolkit/openvino_notebooks/assets/29454499/d5fbbd1a-d484-415c-88cb-9986625b7b11"
            }
          }
        ]
      }
    ],
    "max_completion_tokens": 300,
    "temperature": 0.1
  }'
```

## Using the OpenAPI Spec with Bruno

For collection generation and API testing, import the checked-in spec:

- File: `docs/user-guide/api-docs/openapi.yaml`
- Bruno: **Collections → Import OpenAPI** and select this YAML file

This file is generated from the FastAPI app and is the recommended source for reproducible Bruno collections.
