# Pluggable Vector Database & Storage Backends

The DataPrep microservice is **vector-database agnostic** and **storage agnostic**.
The vector store and the object/blob storage are each selected at startup behind a
factory, so the same service image can run against different backends without code
changes. LangChain integrations (`langchain-vdms`, `langchain-milvus`) are the
common point through which the vector databases are imported and used.

Supported backends:

| Concern        | Setting             | Supported values        | Default |
|----------------|---------------------|-------------------------|---------|
| Vector database| `VECTORDB_BACKEND`  | `vdms`, `milvus`        | `vdms`  |
| Object storage | `STORAGE_BACKEND`   | `minio`, `local`        | `minio` |

The defaults (`vdms` + `minio`) reproduce the historical behavior of this service.

## Architecture

```
src/core/
  vectorstores/
    base.py         # BaseVectorStore ABC: connect, add_embeddings,
                    #   clean_metadata, update_index, health
    vdms_store.py   # VDMS backend (langchain_vdms)
    milvus_store.py # Milvus backend (langchain_milvus)
    metadata.py     # backend-neutral canonical metadata + per-backend adapters
    factory.py      # get_vector_store() — cached singleton by VECTORDB_BACKEND
  storage/
    base.py         # BaseStorage ABC (bucket + object operations)
    minio_storage.py# MinIO backend (wraps the existing MinioClient)
    local_storage.py# Local filesystem backend (bucket == directory)
    factory.py      # get_storage() — cached singleton by STORAGE_BACKEND
```

- Embedding generation is fully separated from persistence. The embedding clients
  (`SimpleVDMSClient`, `SDKVDMSClient` — names retained for compatibility) compute
  or fetch embeddings and then delegate persistence to `get_vector_store()`. They
  no longer import any vector-database SDK directly.
- Both persistence paths route through the same `add_embeddings(...)` contract:
  - frame embeddings (`store_frame_embeddings`)
  - text/summary embeddings (`store_text_embedding` /
    `store_text_embedding_with_vector`, used by the `process_text` endpoint).
- Endpoints and utilities obtain storage through `get_storage()`
  (`get_minio_client()` is retained as a thin backward-compatible shim that now
  returns the active `BaseStorage`).
- The application lifespan calls `vector_store.update_index()` at shutdown — a
  backend-agnostic operation (VDMS persists its descriptor-set index; Milvus is a
  no-op because it indexes eagerly).
- The `/health` endpoint reports `vectordb_backend`, `vectordb_status` and
  `storage_backend` for the active backends.

### The common insert contract

```python
add_embeddings(
    texts: List[str],
    embeddings: List[List[float]],   # precomputed vectors
    metadatas: List[dict],           # canonical, backend-neutral metadata
    ids: Optional[List[str]] = None,
) -> List[str]                       # stored ids, normalized to str
```

- **VDMS** maps this to `VDMS.add_from(...)`.
- **Milvus** maps this to `Milvus.add_embeddings(...)`. Returned int64 primary keys
  are normalized to `str`.

### Canonical metadata

DataPrep writes a single **backend-neutral** metadata dict per embedding. Each
backend adapts it (`clean_metadata`):

- **VDMS** accepts only scalar values, so lists are flattened to comma-separated
  strings and dicts are JSON-encoded (`adapt_for_vdms`).
- **Milvus** uses dynamic fields, so lists and nested values are preserved as-is;
  only `None` values are dropped (`adapt_for_milvus`).

The canonical field names (see `vectorstores/metadata.py::CANONICAL_FIELDS`) are
the contract DataPrep **writes**; they are not tied to any one backend. A retriever
consuming the data maps these to its own query schema.

## Configuration

### Vector database

| Variable           | Applies to | Description                                                        |
|--------------------|------------|--------------------------------------------------------------------|
| `VECTORDB_BACKEND` | all        | `vdms` (default) or `milvus`.                                       |
| `DB_COLLECTION`    | all        | Collection/index name.                                             |
| `VDB_METRIC_TYPE`  | all        | Similarity metric (`IP` default, `L2`).                            |
| `VDB_INDEX_TYPE`   | milvus     | Index type (e.g. `FLAT`).                                          |
| `VDMS_VDB_HOST`    | vdms       | VDMS host.                                                         |
| `VDMS_VDB_PORT`    | vdms       | VDMS port.                                                         |
| `MILVUS_URI`       | milvus     | Full URI (e.g. `http://host:19530`). Overrides host/port when set. |
| `MILVUS_HOST`      | milvus     | Milvus host (used when `MILVUS_URI` is unset).                     |
| `MILVUS_PORT`      | milvus     | Milvus port (default `19530`).                                     |

> **Milvus proxy note:** disable any HTTP proxy for the Milvus host
> (`no_proxy`/`NO_PROXY`). An HTTP proxy in front of localhost/in-cluster gRPC
> causes Milvus startup failures and connection errors. The service sets
> `no_proxy` for the configured Milvus host automatically, but the Milvus
> container stack (etcd/minio/standalone) must also have proxies disabled — see
> `docker/compose-milvus.yaml`.

### Storage

| Variable             | Applies to | Description                                          |
|----------------------|------------|------------------------------------------------------|
| `STORAGE_BACKEND`    | all        | `minio` (default) or `local`.                        |
| `MINIO_ENDPOINT`     | minio      | MinIO endpoint (`host:port`).                        |
| `MINIO_ACCESS_KEY`   | minio      | MinIO access key.                                    |
| `MINIO_SECRET_KEY`   | minio      | MinIO secret key.                                    |
| `MINIO_SECURE`       | minio      | Use HTTPS (`true`/`false`).                          |
| `LOCAL_STORAGE_PATH` | local      | Root directory; each bucket maps to a subdirectory.  |

## Running with the Milvus backend

A ready-to-use example is provided at `docker/compose-milvus.yaml`. It starts a
Milvus 2.6.x standalone stack (etcd + internal MinIO + Milvus), a separate MinIO
for media storage, and the DataPrep service configured with
`VECTORDB_BACKEND=milvus`.

```bash
docker compose -f docker/compose-milvus.yaml up
```

## Adding a new backend

### A new vector database

1. Create `src/core/vectorstores/<name>_store.py` implementing
   `BaseVectorStore` (`connect`, `add_embeddings`, `clean_metadata`,
   `update_index`, `health`).
2. Add a metadata adapter in `metadata.py` if the backend needs a different
   representation (e.g. flatten vs preserve lists).
3. Register the backend in `vectorstores/factory.py::get_vector_store`.
4. Add settings to `src/common/settings.py` and document them here.

### A new storage backend

1. Create `src/core/storage/<name>_storage.py` implementing `BaseStorage`.
2. Register it in `storage/factory.py::get_storage`.
3. Add settings and document them here.

## Testing

- Unit tests: `tests/test_storage_backends.py`, `tests/test_vectorstores.py`
  (factory selection, local storage operations, metadata adapters, the insert
  contract with a mocked backend).
- Milvus integration test: `tests/test_milvus_integration.py` validates the write
  path against a **real** Milvus container (write → read back vectors + metadata).
  It is skipped unless `MILVUS_IT_URI` is set, e.g.:

  ```bash
  MILVUS_IT_URI=http://localhost:19531 poetry run pytest tests/test_milvus_integration.py
  ```

  > A real Milvus container is required — `milvus-lite` is **not** compatible with
  > `langchain-milvus` (its ORM `col` property is unsupported by lite).

## Required downstream changes (informational)

This service was generalized from a VDMS-only dataprep. The legacy
`visual-data-preparation-for-retrieval/milvus` dataprep is **deprecated but kept**.
Backward compatibility with the legacy API is **not** implemented; this section
records what consumers must adapt.

### Legacy `milvus`-dataprep API surface

`GET /v1/dataprep/health`, `GET /v1/dataprep/info`,
`POST /v1/dataprep/ingest` (local `file_dir` OR `file_path` + sidecar meta JSON),
`GET /v1/dataprep/get?file_path=`, `DELETE /v1/dataprep/delete?file_path=`,
`DELETE /v1/dataprep/delete_all`.

### VSQA app usage

The VSQA app
(`suites/metro-ai-suite/visual-search-question-and-answering`) calls only three
dataprep endpoints: `POST /v1/dataprep/ingest`
(`{file_dir, frame_extract_interval, do_detect_and_crop}`),
`DELETE /v1/dataprep/delete_all`, and `GET /v1/dataprep/info`. Retrieval is handled
by a separate `retriever-milvus` service.

### Blockers / changes required to repoint a milvus consumer at this dataprep

1. **Ingestion model.** Legacy milvus-dataprep ingests from a local mounted
   directory (`file_dir`) or `file_path`; this service ingests via MinIO
   (`bucket_name`/`video_id`) or the new local-FS storage backend. There is no
   `file_dir`-style batch ingest endpoint here. Consumers must switch to the
   storage-based ingest flow (or a `file_dir` endpoint would need to be added).
2. **Retriever schema coupling.** The legacy `retriever-milvus` expects a `meta`
   JSON shape (`file_path`, `video_pin_second`, `timestamp`, `type`, `label`;
   collection `default`, IP metric). This dataprep writes the **canonical**
   metadata schema. The Milvus retriever/app must map canonical fields →
   its query schema, for example:

   | Legacy retriever field | Canonical dataprep field      |
   |------------------------|-------------------------------|
   | `file_path`            | `video_url` / `video_rel_url` |
   | `video_pin_second`     | `timestamp`                   |
   | `timestamp`            | `date_time` / `upload_timestamp` |
   | `label`                | `label` (detection crops)     |
   | `type`                 | `processing_mode` / `frame_type` |

3. **No vector-database delete.** This dataprep has no endpoint that deletes
   vector records (`delete_video` only removes objects from storage), whereas the
   legacy milvus-dataprep exposed `delete`/`delete_all`/`get`. If a
   delete-from-vectordb capability is required, a new endpoint plus a `delete`
   method on `BaseVectorStore` must be added (intentionally out of scope today).

4. **Image ingestion — FEATURE GAP.** The legacy milvus-dataprep ingests **images
   and videos** (`.jpg/.png/.jpeg` via `process_image`). This dataprep supports
   **video + text/summary only** — there are no image endpoints. If a consumer
   that relies on image ingestion is repointed here, image ingestion would
   regress. This is documented as an out-of-scope downstream gap; adding an image
   ingestion path is a separate feature decision.
