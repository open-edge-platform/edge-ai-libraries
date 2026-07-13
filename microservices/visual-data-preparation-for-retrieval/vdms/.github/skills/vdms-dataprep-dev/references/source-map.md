<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Source map — VDMS DataPrep

## Entry point

`src/main.py` — FastAPI app with `root_path="/v1/dataprep"`, custom
`HTTPException` handler emitting `DataPrepResponse`, CORS from settings.
Lifespan: **startup** preloads the SDK embedding client
(`preload_sdk_client`) and YOLOX detector (`preload_object_detector`);
**shutdown** persists the VDMS index (`FindDescriptorSet … storeIndex=True`).

## Endpoints (`src/endpoints/<area>/`, one APIRouter each)

| Route | Handler file |
|---|---|
| `GET /health` | `health/check_health.py` |
| `POST /summary` | `document_processing/process_text.py` |
| `POST /videos/minio` | `video_processing/process_minio_video.py` |
| `POST /videos/upload`, `POST /videos/rtsp` | `video_processing/upload_and_process_video.py` |
| `GET /videos` | `video_management/list_videos.py` |
| `GET /videos/download` | `video_management/download_video.py` |
| `DELETE /videos/{bucket}/{video_id}` | `video_management/delete_video.py` |
| `GET /telemetry` | `telemetry/telemetry.py` |

Request/response schemas: `src/common/schema.py` (`VideoRequest`,
`VideoSummaryRequest`, `ObjectDetectionConfig`, `DataPrepResponse`,
`BucketVideoListResponse`, telemetry models).

## The embedding pipeline (`src/core/embedding/`)

| File | Role |
|---|---|
| `simplified_embedding_helper.py` | Orchestrator — `generate_video_embedding[_from_content/_from_uri]`, `generate_text_embedding`; wires telemetry; hands storage to the VDMS client |
| `sdk_embedding_helper.py` | **SDK mode** (~2300 lines): the in-process pipeline — decode → (optional) detect → embed → store; `preload_sdk_client`, worker threads, shared-memory frame pool |
| `simple_client.py` | **API mode**: HTTP client to a separate multimodal-embedding-serving instance (`MULTIMODAL_EMBEDDING_ENDPOINT`) |
| `sdk_client.py` | `SDKVDMSClient` — langchain-vdms `VDMS`/`VDMS_Client`; `store_frame_embeddings`/`store_text_embedding`; batched `video_db.add_from(...)`; embedding-dimension probing (source of the `Dimensions mismatch` error) |
| `decoder.py` | Frame extraction: `SharedMemoryPool`, `VideoFrameExtractor`, `decode_and_batch_generator` (file/bytes/RTSP inputs) |

Mode selection: `EMBEDDING_PROCESSING_MODE` (`sdk` default / `api`) in
`src/common/settings.py`.

## Supporting modules

| Path | Contents |
|---|---|
| `src/core/object_detection/` | `detector.py` (YOLOX via OpenVINO), `yolox_utils.py`, COCO class names; weights land in `DETECTION_MODEL_DIR` (`/app/models/yolox`) |
| `src/core/minio_client.py` | `MinioClient` — bucket/object ops, upload/download/list/delete |
| `src/core/utils/` | `video_utils.py` (fetch from MinIO), `metadata_utils.py`, `config_utils.py`, `file_utils.py`, `common_utils.py` (`get_minio_client`) |
| `src/core/validation.py` | `sanitize_model`, `validate_params` decorator, log sanitizing |
| `src/core/telemetry/` | JSONL store + recorder behind `GET /telemetry` |
| `src/common/settings.py` | pydantic `Settings` — every env var; note `DB_COLLECTION` default `video-rag-test` |
| `src/config.yaml` | frame processing / ROI / YOLOX model config |

## Build & packaging

- `docker/Dockerfile` — multi-stage (`python-base`, `builder-base`, `prod`);
  context must be `microservices/` so
  `visual-data-preparation-for-retrieval/vdms/…` and
  `multimodal-embedding-serving/…` both resolve.
- `build.sh` — the sanctioned build; forwards proxies, `--push` to publish.
- `pyproject.toml` — Poetry, path dep
  `multimodal-embedding-serving = { path = "../../multimodal-embedding-serving" }`,
  group `dev` (pytest/coverage/black/isort); CPU torch wheels are base
  dependencies from the `pytorch-cpu` source.
