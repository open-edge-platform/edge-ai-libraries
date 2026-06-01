# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: api-docs/openapi.yaml
```hide_directive-->

The Multimodal Embedding Serving (MME) microservice exposes REST APIs for embedding generation across text, image, and video inputs.  
The repository OpenAPI spec is available at [`api-docs/openapi.yaml`](./api-docs/openapi.yaml).

## Interactive API Documentation

When the service is running, FastAPI provides interactive docs:

- **Swagger UI**: `http://<HOST_IP>:<EMBEDDING_SERVER_PORT>/docs`
- **ReDoc**: `http://<HOST_IP>:<EMBEDDING_SERVER_PORT>/redoc`
- **OpenAPI JSON**: `http://<HOST_IP>:<EMBEDDING_SERVER_PORT>/openapi.json`

With default settings:

```bash
http://<HOST_IP>:9777/docs
http://<HOST_IP>:9777/redoc
http://<HOST_IP>:9777/openapi.json
```

Replace `<HOST_IP>` with the hostname or IP of the machine running MME.

## API Overview

| Category | Endpoint | Description |
| -------- | -------- | ----------- |
| **Service** | `GET /health` | Returns service/model health status |
| **Models** | `GET /models` | Lists supported model families and current selection |
| **Models** | `GET /model/current` | Returns active model and runtime device configuration |
| **Models** | `GET /model/capabilities` | Returns modalities supported by active model (`text`, `image`, `video`) |
| **Embeddings** | `POST /embeddings` | Generates embeddings for supported input payloads |

## `/embeddings` Request Shape

`POST /embeddings` expects:

- `model`: model identifier (for example, `CLIP/clip-vit-b-16`)
- `input`: one of:
  - `text`
  - `image_url`
  - `image_base64`
  - `video_frames`
  - `video_url`
  - `video_base64`
  - `video_file`
  - `frames_manifest_path` batch (`FramesBatchInput`)
- `encoding_format` *(optional)*: embedding output format string (default: `float`)

Example (text):

```bash
curl --location --request POST 'http://<HOST_IP>:9777/embeddings' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "model": "CLIP/clip-vit-b-16",
    "input": {
      "type": "text",
      "text": "A red car on a city street"
    }
  }'
```

## Using the OpenAPI Spec with Bruno

For tooling and collection generation, import the checked-in spec:

- File: `docs/user-guide/api-docs/openapi.yaml`
- Bruno: **Collections → Import OpenAPI** and select the YAML file

This is the recommended source for reproducible API collections in CI/local workflows.
