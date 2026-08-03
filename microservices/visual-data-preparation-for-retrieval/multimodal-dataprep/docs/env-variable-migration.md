# Environment Variable Migration: multimodal-dataprep → multimodal-dataprep

> **Purpose (temporary tracking doc):** This file records every environment
> variable change introduced while making the old `multimodal-dataprep` microservice
> vector-DB / storage agnostic, renaming it to `multimodal-dataprep`, and
> namespacing all of its configuration under a single `MM_DATAPREP_` prefix. It
> exists to give a single source of truth for the downstream migrations of the
> **LVS**, **VSS**, and **VSQA** applications (docker-compose, Helm, `.env`
> files, and any hard-coded references).
>
> **Keep this file up to date:** any future addition, removal, rename, or
> default-value change to an env var in this microservice MUST be recorded in
> the tables below in the same change/PR.

Last updated: 2026-07-09

---

## 0. Final naming rule (READ FIRST)

Every environment variable the microservice **consumes** is now prefixed with
**`MM_DATAPREP_`** (pydantic-settings `env_prefix="MM_DATAPREP_"`). The Python
setting attribute name is unchanged (`settings.DETECTION_DEVICE`), only the
environment variable name gains the prefix (`MM_DATAPREP_DETECTION_DEVICE`).

> **Naming note:** the embedding-pipeline device (`settings.EMBEDDING_DEVICE`)
> is read from **`MM_DATAPREP_EMBEDDING_DEVICE`**, independent of the standalone
> MME service's own `EMBEDDING_DEVICE`.

Two rename hops happened over the life of this refactor:

1. `VDMS_DATAPREP_*` → `MULTIMODAL_DATAPREP_*` (first generalization), then
2. **everything** → `MM_DATAPREP_*` (this pass), which also stripped the
   `SDK_` prefix from the pipeline-tuning vars and removed the API-mode toggle.

Downstream apps should target the **final** `MM_DATAPREP_*` names (section 1/2).

### Exceptions — intentionally NOT prefixed

Standard / third-party-owned variables the service reads as-is:
`no_proxy`, `NO_PROXY`, `http_proxy`, `https_proxy`, and the OpenVINO-runtime
knobs `OV_NUM_STREAMS`, `OV_PERFORMANCE_HINT_NUM_REQUESTS`,
`PERFORMANCE_HINT_NUM_REQUESTS`.

> The DataPrep-owned performance-mode knob is prefixed: **`MM_DATAPREP_OV_PERFORMANCE_MODE`**
> (default `THROUGHPUT`). It maps to the OpenVINO performance hint. The standalone
> MME service keeps its own unprefixed `OV_PERFORMANCE_MODE`.

### Removed entirely

`EMBEDDING_PROCESSING_MODE` — the "api" embedding path was deleted; the service
now always runs the in-process embedding pipeline. `MM_DATAPREP_DEVICE` was also
removed: there is no longer a baseline device. The embedding-pipeline device is
now set via `MM_DATAPREP_EMBEDDING_DEVICE` and object detection via
`MM_DATAPREP_DETECTION_DEVICE`, each independently (both default to `CPU`). The
container env line `EMBEDDING_DEVICE` was removed from the dataprep service; it
now belongs solely to the standalone MME service.

---

## 1. Full environment-variable contract (final `MM_DATAPREP_*` names)

All variables below are read as `MM_DATAPREP_<NAME>`.

### App / server

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_APP_HOST` | `0.0.0.0` | Host used to build video-download URLs in metadata (compose sets it to the service name). |
| `MM_DATAPREP_APP_PORT` | `8000` | Container listen port. |
| `MM_DATAPREP_LOG_LEVEL` | `INFO` | Application log level. |
| `MM_DATAPREP_EMBEDDING_DEVICE` | `CPU` | Inference device (`CPU`/`GPU`/`NPU`) for the in-process embedding pipeline (maps to `settings.EMBEDDING_DEVICE`; independent of the MME service's `EMBEDDING_DEVICE`). |
| `MM_DATAPREP_USE_OPENVINO` | `true` | Use OpenVINO for the in-process embedding pipeline. |
| `MM_DATAPREP_OV_MODELS_DIR` | `/app/ov_models` | OpenVINO model cache directory. |
| `MM_DATAPREP_ALLOW_ORIGINS` | `*` | CORS allowed origins. |
| `MM_DATAPREP_ALLOW_METHODS` | `*` | CORS allowed methods. |
| `MM_DATAPREP_ALLOW_HEADERS` | `*` | CORS allowed headers. |

### Backend selection (pluggable vector DB + storage)

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_VECTORDB_BACKEND` | `vdms` | Active vector DB: `vdms` or `milvus`. |
| `MM_DATAPREP_STORAGE_BACKEND` | `minio` | Media/artifact storage: `minio` or `local`. |
| `MM_DATAPREP_DB_COLLECTION` | `video-rag-test` | Collection/index name. |
| `MM_DATAPREP_VDB_METRIC_TYPE` | `IP` | Similarity metric (`IP`, `L2`). |
| `MM_DATAPREP_VDB_INDEX_TYPE` | `FLAT` | Vector index type (Milvus). |
| `MM_DATAPREP_LOCAL_STORAGE_PATH` | `/tmp/dataprep/storage` | Root dir for the `local` storage backend. |

### VDMS backend (used when `MM_DATAPREP_VECTORDB_BACKEND=vdms`)

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_VDMS_VDB_HOST` | `""` | VDMS host. |
| `MM_DATAPREP_VDMS_VDB_PORT` | `""` (compose sets `55555`) | VDMS port. |

### Milvus backend (used when `MM_DATAPREP_VECTORDB_BACKEND=milvus`)

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_MILVUS_URI` | `""` | Full URI (e.g. `http://host:19530`); overrides host/port when set. |
| `MM_DATAPREP_MILVUS_HOST` | `""` | Milvus host (used when URI unset). |
| `MM_DATAPREP_MILVUS_PORT` | `19530` | Milvus port. |

### MinIO storage (used when `MM_DATAPREP_STORAGE_BACKEND=minio`)

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_MINIO_ENDPOINT` | `""` | MinIO endpoint (`host:port`). |
| `MM_DATAPREP_MINIO_ACCESS_KEY` | `""` | Access key. |
| `MM_DATAPREP_MINIO_SECRET_KEY` | `""` | Secret key. |
| `MM_DATAPREP_MINIO_SECURE` | `false` | Use HTTPS. |
| `MM_DATAPREP_DEFAULT_BUCKET_NAME` | `video-summary` | Default media bucket. |

### Embedding service

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_EMBEDDING_MODEL_NAME` | `""` | Embedding model name (multimodal e.g. `CLIP/clip-vit-b-32`, or text-only e.g. `QwenText/qwen3-embedding-0.6b`). |
| `MM_DATAPREP_EMBEDDING_BATCH_SIZE` | `32` | Embedding batch size. |
| `MM_DATAPREP_OV_PERFORMANCE_MODE` | `THROUGHPUT` | OpenVINO performance hint for the DataPrep embedding pipeline. |
| `MM_DATAPREP_MAX_PARALLEL_WORKERS` | *(auto)* | Optional hard cap for parallel pipeline workers. |

### Frame extraction / object detection

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_FRAME_INTERVAL` | `15` | Frame sampling interval. |
| `MM_DATAPREP_ENABLE_OBJECT_DETECTION` | `true` | Enable YOLOX object detection. |
| `MM_DATAPREP_DETECTION_CONFIDENCE` | `0.85` | Detection confidence threshold. |
| `MM_DATAPREP_DETECTION_DEVICE` | `CPU` | Dedicated device for object detection (set independently; no baseline fallback). |
| `MM_DATAPREP_DETECTION_MODEL_DIR` | `/app/models/yolox` | YOLOX model directory. |
| `MM_DATAPREP_FRAMES_TEMP_DIR` | `/tmp/dataprep` | Temp dir for extracted frames. |
| `MM_DATAPREP_ROI_CONSOLIDATION_ENABLED` | `false` | Consolidate overlapping detection ROIs. |
| `MM_DATAPREP_ROI_CONSOLIDATION_IOU_THRESHOLD` | `0.2` | IoU threshold for ROI consolidation. |
| `MM_DATAPREP_ROI_CONSOLIDATION_CLASS_AWARE` | `false` | Class-aware ROI consolidation. |
| `MM_DATAPREP_ROI_CONSOLIDATION_CONTEXT_SCALE` | `0.2` | Context padding scale for consolidated ROIs. |

### Pipeline tuning (formerly `SDK_*` — prefix stripped, then `MM_DATAPREP_` applied)

| Old (`SDK_*`) | Final (`MM_DATAPREP_*`) | Default |
|---|---|---|
| `SDK_USE_OPENVINO` | `MM_DATAPREP_USE_OPENVINO` | `true` |
| `SDK_VIDEO_SHM_MAX_BLOCKS` | `MM_DATAPREP_VIDEO_SHM_MAX_BLOCKS` | `512` |
| `SDK_VIDEO_SHM_BLOCK_SIZE` | `MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE` | `6220800` |
| `SDK_VIDEO_EXTRACTION_BATCH_SIZE` | `MM_DATAPREP_VIDEO_EXTRACTION_BATCH_SIZE` | `256` |
| `SDK_PIPELINE_QUEUE_MAXSIZE` | `MM_DATAPREP_PIPELINE_QUEUE_MAXSIZE` | `16` |
| `SDK_PIPELINE_COMPLETION_QUEUE_MAXSIZE` | `MM_DATAPREP_PIPELINE_COMPLETION_QUEUE_MAXSIZE` | `1` |
| `SDK_DETECTION_WORKER_THREADS` | `MM_DATAPREP_DETECTION_WORKER_THREADS` | `2` |
| `SDK_EMBED_WORKER_THREADS` | `MM_DATAPREP_EMBED_WORKER_THREADS` | `2` |
| `SDK_PIPELINE_QUEUE_GET_TIMEOUT_S` | `MM_DATAPREP_PIPELINE_QUEUE_GET_TIMEOUT_S` | `1.0` |
| `SDK_ENABLE_TRACING` | `MM_DATAPREP_ENABLE_TRACING` | `false` |
| `VIDEO_FRAME_DECODER_WORKERS` | `MM_DATAPREP_VIDEO_FRAME_DECODER_WORKERS` | `2` |
| `VIDEO_FRAME_LOG_LEVEL` | `MM_DATAPREP_VIDEO_FRAME_LOG_LEVEL` | `INFO` |
| `SAVE_RUNTIME_PIPELINE_STATS` | `MM_DATAPREP_SAVE_RUNTIME_PIPELINE_STATS` | `false` |

### Telemetry

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_TELEMETRY_FILE_PATH` | *(component default)* | Telemetry output file path. |
| `MM_DATAPREP_TELEMETRY_MAX_RECORDS` | *(component default)* | Max telemetry records retained. |
| `MM_DATAPREP_METRICS_MANAGER_URL` | *(empty / disabled)* | Metrics Manager base URL used to publish completed embedding throughput. |
| `MM_DATAPREP_METRICS_MANAGER_TIMEOUT_SECONDS` | `2.0` | Bounded timeout for each Metrics Manager publish attempt. |

### Batch ingestion

| Env var | Default | Purpose |
|---|---|---|
| `MM_DATAPREP_INGEST_DATA_ROOT` | `/tmp/dataprep/ingest` | Container root for `POST /media/ingest-dir`; requested paths are constrained to this root (no traversal). |
| `MM_DATAPREP_INGEST_DATA_ROOT_HOST` | `""` | Host path bind-mounted at the ingest root. When set, the `source_path` metadata of directory-ingested media is recorded in host terms so consumers sharing the mount can locate the original file. Empty records the container path as-is. |
| `MM_DATAPREP_BATCH_MAX_ITEMS` | `100` | Maximum items (files/videos) accepted in a single batch job. |
| `MM_DATAPREP_BATCH_JOB_RETENTION` | `200` | Max finished batch jobs retained in memory for status polling. |

> `MM_DATAPREP_INGEST_DATA_ROOT_HOST` is both a Compose helper (it selects the host
> directory bind-mounted to `MM_DATAPREP_INGEST_DATA_ROOT`) and an app-read setting
> (it maps recorded `source_path` values back to host terms).

---

## 2. Branded rename history (first hop, for reference)

| Original (multimodal-dataprep) | Intermediate | Final |
|---|---|---|
| `VDMS_DATAPREP_DEVICE` | `MULTIMODAL_DATAPREP_DEVICE` | `MM_DATAPREP_EMBEDDING_DEVICE` (embedding-pipeline device; the baseline `MM_DATAPREP_DEVICE` was later dropped) |
| `VDMS_DATAPREP_LOG_LEVEL` | `MULTIMODAL_DATAPREP_LOG_LEVEL` | `MM_DATAPREP_LOG_LEVEL` |
| `VDMS_DATAPREP_HOST_PORT` | `MULTIMODAL_DATAPREP_HOST_PORT` | `MM_DATAPREP_HOST_PORT` (compose host-port var) |

**Migration action for LVS/VSS/VSQA:** replace any `VDMS_DATAPREP_*` /
`MULTIMODAL_DATAPREP_*` / `SDK_*` / `EMBEDDING_PROCESSING_MODE` references with
the final `MM_DATAPREP_*` names in section 1, and drop `EMBEDDING_PROCESSING_MODE`.

---

## 3. Compose-side operator variables (not read by the app directly)

`docker/compose*.yaml` still accept several **operator/wrapper** variables that
are substituted into the container env or shared with sibling services (MinIO).
These are set by `setup.sh` and are intentionally left unprefixed because they
are shared or host-scoped,
e.g.: `MINIO_HOST`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `INDEX_NAME`,
`VS_INDEX_NAME`, `DEFAULT_BUCKET_NAME`, `EMBEDDING_MODEL_NAME`,
`OV_MODELS_DIR`, `YOLOX_MODELS_MOUNT_PATH`, `VDMS_VDB_HOST`,
`VDMS_VDB_HOST_PORT`, `HOST_IP`, `REGISTRY`, `TAG`, `PROJECT_NAME`.

The dataprep-branded wrapper vars WERE renamed to their `MM_DATAPREP_` form in
the setup scripts: `MM_DATAPREP_HOST_PORT`, `MM_DATAPREP_EMBEDDING_DEVICE`,
`MM_DATAPREP_DETECTION_DEVICE`, `MM_DATAPREP_OV_PERFORMANCE_MODE`,
`MM_DATAPREP_LOG_LEVEL`, `MM_DATAPREP_USE_OPENVINO`, and the former `SDK_*`
tuning knobs. The setup scripts now export every app-consumed knob under its
final `MM_DATAPREP_*` name directly (no unprefixed→prefixed compose mapping).

---

## 4. Compose-only infra knobs (Milvus stack, `compose-milvus.yaml`)

| Variable | Default | Purpose |
|---|---|---|
| `MILVUS_HOST_PORT` | `19530` | Host port for the standalone Milvus service. |
| `MILVUS_METRICS_HOST_PORT` | `9091` | Host port for Milvus metrics endpoint. |

---

## 5. Retained VDMS-specific names (unchanged — do NOT rename the backend)

Backend-specific to VDMS; only relevant when
`MM_DATAPREP_VECTORDB_BACKEND=vdms` (the default). The **backend identity**
(`vdms`), the connection var *stems* (`VDMS_VDB_HOST`/`VDMS_VDB_PORT`), and the
`vdms-vector-db` service keep the VDMS name. Note the app-read connection vars
still carry the `MM_DATAPREP_` prefix (`MM_DATAPREP_VDMS_VDB_HOST/PORT`); the
compose host-port wrapper `VDMS_VDB_HOST_PORT` stays unprefixed.

---

## 6. Change log

| Date | Change | By |
|---|---|---|
| 2026-07-08 | Initial capture: `VDMS_DATAPREP_*`→`MULTIMODAL_DATAPREP_*` renames; new backend-selection (`VECTORDB_BACKEND`, `STORAGE_BACKEND`, `MILVUS_*`, `VDB_*`, `LOCAL_STORAGE_PATH`) and NPU (`DETECTION_DEVICE`) vars. | integration |
| 2026-07-09 | Applied single `MM_DATAPREP_` prefix to ALL app-consumed env vars (pydantic `env_prefix`); stripped `SDK_` prefix from pipeline-tuning vars; **removed `EMBEDDING_PROCESSING_MODE` and the API embedding mode** (SDK/in-process pipeline is now the only path); removed the redundant container `EMBEDDING_DEVICE` line. Kept `no_proxy`/OpenVINO-runtime vars unprefixed. | integration |
| 2026-07-09 | **Removed the baseline `MM_DATAPREP_DEVICE`.** Device selection is now per-component and independent: embedding uses **`MM_EMBEDDING_DEVICE`** (maps to `settings.DEVICE` via `validation_alias`), detection uses **`MM_DATAPREP_DETECTION_DEVICE`**; both default to `CPU` with no cascade. The standalone MME service's `EMBEDDING_DEVICE` is now fully independent of DataPrep. Updated all 3 compose files + both setup scripts. | integration |
| 2026-07-09 | Renamed the DataPrep OpenVINO performance-mode knob `OV_PERFORMANCE_MODE` → **`MM_OV_PERFORMANCE_MODE`** (default `THROUGHPUT`; still falls back to the third-party `OPENVINO_PERFORMANCE_MODE`). The standalone MME service keeps its own unprefixed `OV_PERFORMANCE_MODE`. Updated all 3 compose files + both setup scripts. | integration |
| 2026-07-14 | **Normalized naming to a single `MM_DATAPREP_` prefix.** Renamed the two remaining short-prefix vars `MM_EMBEDDING_DEVICE` → **`MM_DATAPREP_EMBEDDING_DEVICE`** (dropped the pydantic `validation_alias`; `settings.DEVICE` → `settings.EMBEDDING_DEVICE`) and `MM_OV_PERFORMANCE_MODE` → **`MM_DATAPREP_OV_PERFORMANCE_MODE`** (now a first-class `settings.OV_PERFORMANCE_MODE` field; the `OPENVINO_PERFORMANCE_MODE` fallback was removed). Renamed `MM_DATAPREP_MULTIMODAL_EMBEDDING_MODEL_NAME` → **`MM_DATAPREP_EMBEDDING_MODEL_NAME`** (`settings.MULTIMODAL_EMBEDDING_MODEL_NAME` → `settings.EMBEDDING_MODEL_NAME`) since the loaded SDK model can be text-only (e.g. `QwenText/qwen3-embedding-0.6b`) and is not necessarily multimodal; also removed the dead `use_qwen_for_long_text`/`qwen_threshold` hint from `generate_text_embedding`. Collapsed the redundant unprefixed→prefixed compose mappings so `setup.sh` exports every app-consumed knob under its final `MM_DATAPREP_*` name directly. | integration |
| 2026-08-02 | **`MM_DATAPREP_INGEST_DATA_ROOT_HOST` is now read by the app** (previously Compose-only). Directory ingest records a `source_path` on every embedding, expressed in host terms when this var is set, so consumers sharing the ingest mount can read the original media in place. Related additions (no new env vars): `store_copy` and `metadata` on `POST /media/ingest-dir`, user-metadata passthrough from `meta/<basename>.json` sidecars, `content_type` on video embeddings, and `DELETE /media/{bucket_name}`. | integration |
| 2026-08-03 | **Media ingested by reference is now served like stored media** (no new env vars). A `store_copy=false` ingest writes a `.source_ref` path sidecar next to the existing dedup markers, so `GET /media` lists the item with `"stored": false` + its host-visible `source_path`, and `GET /media/download` streams it from the ingest mount with full HTTP Range support. The recorded path is re-validated against `MM_DATAPREP_INGEST_DATA_ROOT` on every read, so nothing outside the mount can be served. | integration |
| 2026-07-20 | **Added batch ingestion** (async job engine + `POST /media/upload/batch`, `POST /media/process/batch`, `POST /media/ingest-dir`, `GET`/`DELETE /media/jobs/{job_id}`). New env vars: `MM_DATAPREP_INGEST_DATA_ROOT` (default `/tmp/dataprep/ingest`; traversal-constrained root for directory ingest), `MM_DATAPREP_BATCH_MAX_ITEMS` (default `100`), `MM_DATAPREP_BATCH_JOB_RETENTION` (default `200`). Compose-only helper `MM_DATAPREP_INGEST_DATA_ROOT_HOST` bind-mounts a host dir to the ingest root. | integration |
