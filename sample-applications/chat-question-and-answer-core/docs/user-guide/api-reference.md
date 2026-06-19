# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: _assets/chatqna-api.yml
```hide_directive-->

The Chat Question-and-Answer Core sample application exposes REST APIs for health checks, document ingestion, chat inference, and runtime-specific model/device inspection.

The full OpenAPI specification is available in [`_assets/chatqna-api.yml`](_assets/chatqna-api.yml).

## Interactive API Documentation

When the application is running, interactive API documentation is available through Swagger UI.

| Service | URL |
| ------- | --- |
| **Chat Q&A Core API docs** | `http://<HOST_IP>:8102/v1/chatqna/docs` |
| **OpenAPI JSON** | `http://<HOST_IP>:8102/v1/chatqna/openapi.json` |

Replace `<HOST_IP>` with the hostname or IP address of the machine running the application.

## Base URL

All endpoint paths in this page are relative to the following base URL:

```text
http://<HOST_IP>:8102/v1/chatqna
```

Examples in this guide assume Docker Compose default networking and ports from the getting-started flow.

## API Overview

| Category | Endpoints | Description |
| -------- | --------- | ----------- |
| **Health API** | `GET /health` | Service health check. |
| **Model API** | `GET /model`, `GET /ollama-models`, `GET /ollama-model` | Runtime model metadata and model status. |
| **Document Ingestion API** | `GET /documents`, `POST /documents`, `DELETE /documents` | Document upload/listing/deletion for vector store management. |
| **Device API (OpenVINO only)** | `GET /devices`, `GET /devices/{device}` | OpenVINO device discovery and device properties. |
| **Chat API** | `POST /chat` | Question answering with streamed or non-streamed response. |

> **Runtime note:**
> - `GET /devices` and `GET /devices/{device}` are available when using the `OPENVINO` runtime.
> - `GET /ollama-models` and `GET /ollama-model` are available when using the `OLLAMA` runtime.

## Endpoints

### `GET /health`

Returns service liveness information.

Example:

```bash
curl -X GET "http://<HOST_IP>:8102/v1/chatqna/health"
```

Success response (`200`):

```json
{
	"status": "Success",
	"message": "Service is up and running."
}
```

### `GET /model`

Returns the currently configured LLM model identifier.

Example:

```bash
curl -X GET "http://<HOST_IP>:8102/v1/chatqna/model"
```

Typical response (`200`):

```json
{
	"status": "Success",
	"llm_model": "<model-id>"
}
```

### `GET /documents`

Returns the list of ingested documents currently present in the vector store.

Example:

```bash
curl -X GET "http://<HOST_IP>:8102/v1/chatqna/documents"
```

Success response (`200`):

```json
{
	"status": "Success",
	"metadata": {
		"documents": ["doc1.pdf", "doc2.txt"]
	}
}
```

### `POST /documents`

Uploads one or more documents and creates embeddings.

- Supported formats: `pdf`, `txt`, `docx`
- Content type: `multipart/form-data`
- Form field: `files`

Example:

```bash
curl -X POST "http://<HOST_IP>:8102/v1/chatqna/documents" \
	-H "Content-Type: multipart/form-data" \
	-F "files=@./doc1.pdf" \
	-F "files=@./doc2.txt"
```

Success response (`200`):

```json
{
	"status": "Success",
	"message": "Files have been successfully ingested and embeddings created.",
	"metadata": {
		"documents": ["doc1.pdf", "doc2.txt"]
	}
}
```

Common errors:

- `400`: Invalid file format.
- `500`: Ingestion or embedding creation failure.

### `DELETE /documents`

Deletes embeddings for a specific document or deletes all embeddings.

Query parameters:

- `document` (string, optional): Document filename to delete.
- `delete_all` (boolean, optional): If `true`, deletes all embeddings.

Examples:

```bash
# Delete all embeddings
curl -X DELETE "http://<HOST_IP>:8102/v1/chatqna/documents?delete_all=true"

# Delete one document's embeddings
curl -X DELETE "http://<HOST_IP>:8102/v1/chatqna/documents?document=doc1.pdf"
```

Responses:

- `204`: Deleted successfully.
- `422`: Missing required query context (for example no `document` when `delete_all=false`).
- `404`: No documents found in vector store.
- `500`: Internal error.

### `GET /devices` (OpenVINO runtime)

Returns available OpenVINO target devices.

Example:

```bash
curl -X GET "http://<HOST_IP>:8102/v1/chatqna/devices"
```

Success response (`200`):

```json
{
	"devices": ["CPU", "GPU"]
}
```

### `GET /devices/{device}` (OpenVINO runtime)

Returns OpenVINO properties for a specific device.

Example:

```bash
curl -X GET "http://<HOST_IP>:8102/v1/chatqna/devices/CPU"
```

Responses:

- `200`: Device properties object.
- `404`: Device not found.
- `500`: Internal error.

### `POST /chat`

Submits a question and returns either a standard JSON answer or a streamed SSE response.

Request body:

```json
{
	"input": "What is Retrieval-Augmented Generation?",
	"stream": true
}
```

Fields:

- `input` (string, required): User question.
- `stream` (boolean, optional, default `true`):
	- `true`: Returns `text/event-stream`.
	- `false`: Returns regular JSON.

Examples:

```bash
# Streamed response (default)
curl -N -X POST "http://<HOST_IP>:8102/v1/chatqna/chat" \
	-H "Content-Type: application/json" \
	-d '{"input":"What is load_chain?","stream":true}'

# Non-streamed JSON response
curl -X POST "http://<HOST_IP>:8102/v1/chatqna/chat" \
	-H "Content-Type: application/json" \
	-d '{"input":"What is load_chain?","stream":false}'
```

Typical non-stream response (`200`):

```json
{
	"status": "Success",
	"metadata": "<answer text>"
}
```

Common errors:

- `422`: Missing or empty `input`.
- `500`: Inference or processing failure.

### `GET /ollama-models` (Ollama runtime)

Returns the list of currently loaded Ollama models.

Example:

```bash
curl -X GET "http://<HOST_IP>:8102/v1/chatqna/ollama-models"
```

Success response (`200`):

```json
{
	"model_list": ["llama2", "mistral", "phi3"]
}
```

### `GET /ollama-model` (Ollama runtime)

Returns metadata for a specific Ollama model.

Query parameters:

- `model_id` (string, optional): Model identifier.

Example:

```bash
curl -X GET "http://<HOST_IP>:8102/v1/chatqna/ollama-model?model_id=llama2"
```

Responses:

- `200`: Model metadata object.
- `404`: Model not found.
- `500`: Internal error.

## Using the OpenAPI Specification Offline

You can import [`docs/user-guide/_assets/chatqna-api.yml`](_assets/chatqna-api.yml) into OpenAPI-compatible tools:

- [Swagger Editor](https://editor.swagger.io/) to inspect schemas and run requests.
- [Bruno](https://www.usebruno.com/) to generate an API collection.

For complete request and response schemas, use either the embedded specification on this page or the live Swagger UI endpoint from a running deployment.
