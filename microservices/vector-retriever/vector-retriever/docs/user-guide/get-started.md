# Get Started

This guide provides step-by-step instructions to quickly deploy and test the **Vector Retriever microservice**.

## Prerequisites

Before you begin, confirm the following:

- **System Requirements**: Your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker if needed. See [Get Docker](https://docs.docker.com/get-docker/).
- **Embedding Service Plan**: Use the local multimodal-embedding-serving (MME) overlay started by `setup.sh`, or provide an external `EMBEDDINGS_ENDPOINT`.

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Environment Variables

The table below lists the core configuration knobs. `setup.sh` seeds defaults, but you can override them before sourcing the script.

Core variables:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `RETRIEVER_BACKEND` | No | `vdms` | Backend flavor: `vdms`, `milvus`, `pgvector`, `faiss`. |
| `MULTIMODAL_EMBEDDING_ENDPOINT` | No | `http://multimodal-embedding-serving:8000/embeddings` | VSS-style embedding endpoint name used by `setup.sh` and compose overlays. |
| `EMBEDDINGS_ENDPOINT` | No | value of `MULTIMODAL_EMBEDDING_ENDPOINT` | Runtime embedding API endpoint consumed by the retriever service. |
| `EMBEDDING_MODEL_NAME` | Yes | _(empty)_ | Embedding model name sent to embedding API. |
| `INDEX_NAME` | No | `video_frame_embeddings` | Vector collection/index name. |
| `DEFAULT_TOP_K` | No | `20` | Default `top_k` when omitted in query. |
| `MAX_TOP_K` | No | `1000` | Maximum allowed `top_k`. |
| `VECTOR_RETRIEVER_HOST_PORT` | No | `6008` | Host port published by Docker Compose. |
| `VECTOR_RETRIEVER_LOG_LEVEL` | No | `INFO` | Log level passed into the container as `LOG_LEVEL`. |

VDMS backend:

| Variable | Required | Default |
| --- | --- | --- |
| `VDMS_VDB_HOST` | Yes for `vdms` | `vdms-vector-db` |
| `VDMS_VDB_PORT` | Yes for `vdms` | `55555` |
| `SEARCH_ENGINE` | No | `FaissFlat` |
| `DISTANCE_STRATEGY` | No | `IP` |

Milvus backend:

| Variable | Required | Default |
| --- | --- | --- |
| `MILVUS_URI` | Yes for `milvus` | `http://milvus-server:19530` |
| `MILVUS_TOKEN` | No | _(empty)_ |
| `MILVUS_DB_NAME` | No | _(empty)_ |
| `MILVUS_INDEX_TYPE` | No | `FLAT` |
| `MILVUS_METRIC_TYPE` | No | `L2` |

PGVector backend:

| Variable | Required | Default |
| --- | --- | --- |
| `PGVECTOR_CONNECTION_STRING` | Yes for `pgvector` | `postgresql+psycopg://postgres:postgres@pgvector-db:5432/postgres` |

FAISS backend:

| Variable | Required | Default |
| --- | --- | --- |
| `FAISS_INDEX_PATH` | No | _(empty)_ |

MME embedding backend (used by all overlays):

| Variable | Required | Default |
| --- | --- | --- |
| `EMBEDDING_MODEL_NAME` | Yes | _(empty)_ |
| `EMBEDDING_DEVICE` | No | `CPU` |
| `EMBEDDING_USE_OV` | No | `true` |
| `EMBEDDING_SERVER_PORT` | No | `9777` |
| `MULTIMODAL_EMBEDDING_HOST` | No | `multimodal-embedding-serving` |
| `MULTIMODAL_EMBEDDING_PORT` | No | `8000` |
| `MULTIMODAL_EMBEDDING_ENDPOINT` | No | `http://multimodal-embedding-serving:8000/embeddings` |

## Set Environment Values

Set the required environment variables before launching the service.

```bash
# Choose one backend: vdms | milvus | pgvector | faiss
export RETRIEVER_BACKEND=vdms
export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32"
# Optional when using an external embedding service instead of the local MME overlay:
# export EMBEDDINGS_ENDPOINT=http://<embedding-service-host>:<port>/embeddings
```

> **_NOTE:_** For valid `EMBEDDING_MODEL_NAME` values, see the MME supported models list: [Supported Models](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/multimodal-embedding-serving/docs/user-guide/supported-models.md).

Supported backend values for `RETRIEVER_BACKEND` are `vdms`, `milvus`, `pgvector`, and `faiss`.
`setup.sh` defaults `EMBEDDINGS_ENDPOINT` to the local MME overlay unless you override it.

### Configure the registry

```bash
export REGISTRY_URL=intel
export TAG=latest
```

### Optional Environment Variables

The microservice supports additional optional variables to tune filters, limits, backend connectivity, and logging.

**Quick Configuration Examples**:

```bash
# Default VDMS backend
export RETRIEVER_BACKEND=vdms
export VDMS_VDB_HOST=vdms-vector-db
export VDMS_VDB_PORT=55555

# Milvus backend
export RETRIEVER_BACKEND=milvus
export MILVUS_URI=http://milvus-server:19530

# PGVector backend
export RETRIEVER_BACKEND=pgvector
export PGVECTOR_CONNECTION_STRING=postgresql+psycopg://user:pass@host:5432/db

# FAISS backend (optional persisted local index)
export RETRIEVER_BACKEND=faiss
export FAISS_INDEX_PATH=./data/faiss_index
```

**Key Environment Variables**:

- **DEFAULT_TOP_K**: Default top-k returned when request omits `top_k`.
- **MAX_TOP_K**: Maximum top-k allowed by request validation.
- **VECTOR_RETRIEVER_HOST_PORT**: Host port used to expose service (default `6008`).
- **VECTOR_RETRIEVER_LOG_LEVEL**: Runtime logging level.

`time_filter` is applied to the `created_at` metadata field. For time filtering on any other field, use `where` with `gt`, `gte`, `lt`, `lte`, or `between`.

### Set the environment variables

Set the environment with default values by running the command below. Run this again whenever environment values change.

```bash
source setup.sh --nosetup
```

## Start the Service (Recommended: `source setup.sh`)

Use `setup.sh` as the default startup path. It validates required environment variables, renders `.env`, selects the backend compose overlay, and starts the stack.

You can [build the Docker image](./how-to-build-from-source.md#steps-to-build) or pull a prebuilt image from the configured registry and tag.

### Start using `RETRIEVER_BACKEND`

```bash
export RETRIEVER_BACKEND=vdms
source setup.sh
```

### Start with one-shot backend flags

Each one-shot flag automatically sets `RETRIEVER_BACKEND` to the matching backend for the current shell before startup.

```bash
source setup.sh --up-with-vdms
source setup.sh --up-with-milvus
source setup.sh --up-with-pgvector
source setup.sh --up-with-faiss
```

When you use the backend overlay flow above, Docker starts:

- `vector-retriever`
- `multimodal-embedding-serving`
- Local backend service for `vdms`, `milvus`, or `pgvector` (FAISS is in-process and does not start a separate database container)

### Use an external backend service

If your vector database is already running outside this compose stack, set backend connection variables to that external endpoint and start only the retriever stack.

Examples:

- `VDMS_VDB_HOST` and `VDMS_VDB_PORT` for VDMS
- `MILVUS_URI` for Milvus
- `PGVECTOR_CONNECTION_STRING` for PGVector

Then run:

```bash
source setup.sh --nosetup
docker compose -f docker/compose.yaml up -d --build
```

## Manual Docker Compose (Advanced)

Use direct compose commands only when you want explicit control or troubleshooting behavior.

Start with local backend overlay services:

```bash
docker compose -f docker/compose.yaml -f docker/compose.${RETRIEVER_BACKEND}.yaml up -d --build
```

Start retriever-only (for external backend services):

```bash
docker compose -f docker/compose.yaml up -d --build
```

`setup.sh` remains recommended because manual compose does not perform setup-time validation and convenience handling.

## Verify Deployment

```bash
curl --location --request GET 'http://localhost:6008/health'
curl --location --request GET 'http://localhost:6008/ready'
```

## Cleanup and Stop

Use the commands below based on how much cleanup you need.

### Stop running services (`--down`)

```bash
source setup.sh --down
```

This stops vector-retriever and overlay services across all backend compose files.

### Stop services and remove stack data (`--clean-data`)

```bash
source setup.sh --clean-data
```

This stops services, removes compose orphans, and removes only this stack's named volumes.

## Sample CURL Commands

All requests target `http://localhost:6008`.

### Health Check

```bash
curl --location --request GET 'http://localhost:6008/health'
```

### Readiness Check

```bash
curl --location --request GET 'http://localhost:6008/ready'
```

### Filter Capabilities (All Backends)

```bash
curl --location --request GET 'http://localhost:6008/capabilities/filters'
```

### Filter Capabilities (Single Backend)

```bash
curl --location --request GET 'http://localhost:6008/capabilities/filters?backend=milvus'
```

### Query with `where` and Top-K

```bash
curl --location 'http://localhost:6008/query' \
--header 'Content-Type: application/json' \
--data '[
  {
    "query_id": "q1",
    "query": "red car",
    "where": {
      "field": "tags",
      "op": "contains_any",
      "value": ["traffic"]
    },
    "top_k": 10
  }
]'
```

`where` is the preferred filter contract. Legacy `tags`, `time_filter`, and `filters`
fields are still accepted for backward compatibility.

### Query with Image Input (base64)

```bash
curl --location 'http://localhost:6008/query' \
--header 'Content-Type: application/json' \
--data '[
  {
    "query_id": "img1",
    "image": {
      "type": "image_base64",
      "image_base64": "<base64-encoded-image-data>"
    },
    "top_k": 5
  }
]'
```

### Query with Image Input (URL)

```bash
curl --location 'http://localhost:6008/query' \
--header 'Content-Type: application/json' \
--data '[
  {
    "query_id": "img2",
    "image": {
      "type": "image_url",
      "image_url": "https://example.com/photo.jpg"
    },
    "top_k": 5
  }
]'
```

> **_NOTE:_** `query` and `image` are mutually exclusive. Providing both returns `422`.

### Query with Time Filter

```bash
curl --location 'http://localhost:6008/query' \
--header 'Content-Type: application/json' \
--data '[
  {
    "query_id": "q2",
    "query": "person near crosswalk",
    "time_filter": {
      "start": "2026-03-01T00:00:00Z",
      "end": "2026-03-22T23:59:59Z"
    }
  }
]'
```

### Query with Dynamic Filters

```bash
curl --location 'http://localhost:6008/query' \
--header 'Content-Type: application/json' \
--data '[
  {
    "query_id": "q3",
    "query": "bus on main road",
    "filters": {
      "bucket_name": {"op": "in", "value": ["north", "west"]},
      "timestamp": {"op": "gte", "value": 10}
    }
  }
]'
```

## Run Tests (Unit and Functional)

Run tests from this service root directory.

### Install test dependencies

Pick the backend dependency group you want to validate (`vdms`, `milvus`, `pgvector`, or `faiss`) and install with dev dependencies:

```bash
export RETRIEVER_BACKEND=vdms
poetry install --only "main,backend-${RETRIEVER_BACKEND},dev" --no-root
```

### Run unit tests

Unit tests exclude dockerized backend functional tests:

```bash
PYTHONPATH=. poetry run pytest -q tests --ignore=tests/functional
```

You can also run the core unit suite directly:

```bash
PYTHONPATH=. poetry run pytest -q \
  tests/test_schema.py \
  tests/test_filters.py \
  tests/test_backend_factory.py \
  tests/test_service.py \
  tests/test_main.py
```

### Run functional backend tests

Functional tests bring up docker compose backend overlays, seed test data, and verify the filter matrix end-to-end.

Run all backend functional tests:

```bash
RUN_FUNCTIONAL_BACKEND_TESTS=1 PYTHONPATH=. poetry run pytest -q tests/functional
```

Run one backend only (example: PGVector):

```bash
RUN_FUNCTIONAL_BACKEND_TESTS=1 PYTHONPATH=. poetry run pytest -q tests/functional/test_pgvector_filters.py
```

> **_NOTE:_** Functional tests are intentionally heavier than unit tests and require Docker.

## Troubleshooting

- **Container fails to start**

  - Run `docker logs vector-retriever` (or the compose service container name) to inspect startup failures.
  - Ensure required ports (default `6008`) are available.

- **Readiness check fails**

  - Confirm the embedding endpoint configured by `EMBEDDINGS_ENDPOINT` is reachable from the container.
  - Confirm backend-specific connectivity (VDMS/Milvus/PGVector) is valid.

- **No results returned**

  - Verify index/collection name (`INDEX_NAME`) matches where embeddings were stored.
  - Reduce filters temporarily to isolate backend filter translation issues.

- **Configuration changes not applied**

  - Re-run `source setup.sh` after changing environment variables.
  - Use `source setup.sh --conf` to inspect rendered compose configuration.

## Supporting Resources

- [Overview](Overview.md)
- [Overview and Architecture](overview-architecture.md)
- [API Reference](api-reference.md)
- [Filter Grammar](filter-grammar.md)
- [OpenAPI Specification](api-docs/openapi.yaml)
- [System Requirements](system-requirements.md)
- [How to Build from Source](how-to-build-from-source.md)
- [Add New Retriever Backend](add-new-retriever-backend.md)
- [Release Notes](release-notes.md)
