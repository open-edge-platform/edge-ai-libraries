---
name: multimodal-dataprep-dev
description: >
  Develop and debug the Multimodal DataPrep microservice: its FastAPI media
  endpoints, in-process embedding pipeline, batch jobs, object detection,
  telemetry and Metrics Manager publishing, and pluggable VDMS/Milvus vector
  stores plus MinIO/local storage. Use when changing source, adding a backend,
  running pytest/coverage/format checks, or building the service image. Use
  multimodal-dataprep-user for deployment and API-consumer workflows.
---

# Multimodal DataPrep — Dev

Work from
`microservices/visual-data-preparation-for-retrieval/multimodal-dataprep/`
inside an `edge-ai-libraries` checkout. If the request only deploys or consumes
the service, use
[`../multimodal-dataprep-user/SKILL.md`](../multimodal-dataprep-user/SKILL.md).

## Start with the relevant reference

| Reference | Read when |
|---|---|
| [`references/source-map.md`](./references/source-map.md) | Locating endpoints, pipeline code, backend abstractions, or configuration |
| [`references/testing-and-build.md`](./references/testing-and-build.md) | Installing dependencies, testing, formatting, building, or debugging containers |

Example tasks:

| Example | Purpose |
|---|---|
| [onboard-embedding-model.md](./example-prompts/onboard-embedding-model.md) | Exercise a different embedding model safely |
| [update-test-cases.md](./example-prompts/update-test-cases.md) | Add coverage for a source change |

## Build-context rule

Use `./build.sh`; do not run `docker build ... .` from this directory. The
Dockerfile copies both this service and the sibling
`multimodal-embedding-serving` source, so its context must be
`microservices/`. `build.sh` supplies that context.

## Local development loop

```bash
poetry install --with dev
poetry run python -m pytest tests
poetry run coverage run --rcfile ./pyproject.toml -m pytest tests
poetry run coverage report -m
poetry run black --check src tests
poetry run isort --check-only src tests
```

Run a focused test file while iterating:

```bash
poetry run python -m pytest tests/test_vectorstores.py
```

Do not conceal collection failures or attribute unrelated failures to the
current change. See
[`references/testing-and-build.md`](./references/testing-and-build.md).

## Build and run

`setup.sh` must be sourced. With no argument it exports defaults and creates the
YOLOX model volume; it does not start the stack.

```bash
export MINIO_ROOT_USER='<user>'
export MINIO_ROOT_PASSWORD='<strong-password>'
export EMBEDDING_MODEL_NAME='CLIP/clip-vit-b-32'
source ./setup.sh --nosetup

./build.sh
docker compose -f docker/compose.yaml up -d --build
```

Other supported setup actions are `--conf`, `--down`, `--build [custom-tag]`,
and `--nd` (foreground `docker compose ... up --build`).

For Milvus, use `docker/compose-milvus.yaml`. For local media storage, layer
`docker/compose.storage-local.yaml` after the default compose file.

## Current architecture

`src/main.py` creates the FastAPI app at `/v1/dataprep`, starts the optional
Metrics Manager publisher, preloads the embedding client and YOLOX detector,
and asks the active vector store to update its index during shutdown.

Requests flow through `src/endpoints/` into
`src/core/embedding/embedding_orchestrator.py`. Video work is executed by the
threaded/shared-memory pipeline in `embedding_helper.py`; `client.py` wraps the
in-process model from the sibling embedding package and persists vectors
through `src/core/vectorstores/`. Media bytes and metadata go through
`src/core/storage/`.

## Change rules

- Preserve backend neutrality. Use `get_vector_store()` and `get_storage()`
  rather than importing a concrete backend in endpoint or orchestration code.
- Keep search/query behavior out of this service; `BaseVectorStore` covers
  ingestion-time add, delete, health, and index-update operations.
- Add endpoint schemas in `src/common/schema.py` and include routers in
  `src/main.py`.
- Keep media routes under `/media`; supported inputs include MP4 video and
  common image formats, plus text summaries at `/summary`.
- Mock external storage, model, and vector-store calls in unit tests. The
  Milvus integration test is opt-in through `MILVUS_IT_URI`.
- Add the repository SPDX header to every new source, config, test, or
  documentation file.
- Never commit credentials.

## Important configuration facts

| Fact | Impact |
|---|---|
| All application settings use Pydantic's `MM_DATAPREP_` prefix | Set container variables such as `MM_DATAPREP_VECTORDB_BACKEND`, `MM_DATAPREP_STORAGE_BACKEND`, and `MM_DATAPREP_EMBEDDING_MODEL_NAME` |
| `setup.sh` sets `INDEX_NAME=video-rag`; default compose maps it to `MM_DATAPREP_DB_COLLECTION` | For a one-off VDMS collection, set `INDEX_NAME` after sourcing and before Compose |
| Milvus collection names cannot contain hyphens | `compose-milvus.yaml` uses `MILVUS_INDEX_NAME` with default `video_rag` |
| Changing embedding dimensions is incompatible with an existing collection | Choose a fresh collection or obtain confirmation before deleting data |
| YOLOX weights are downloaded on first use | An offline first run can leave object detection unavailable while other ingestion continues |
| Metrics Manager publishing is optional | It is enabled only when `MM_DATAPREP_METRICS_MANAGER_URL` is non-empty and must not delay ingestion |
