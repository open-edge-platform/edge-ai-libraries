<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Mode: `--search` (Video Search only)

Natural-language search over a video library using multimodal embeddings. No
summarization/VLM stack — so the VLM/whisper/OD vars are **not** required.

## Deploy

```bash
source setup.sh --search
bash -c 'source setup.sh --search config'   # dry-run
```

## Required shell env vars

Common to all deploy modes:
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`RABBITMQ_USER`, `RABBITMQ_PASSWORD`.

Search-specific:
- `MULTIMODAL_EMBEDDING_MODEL` — required for both SDK and API embedding modes.

`EMBEDDING_PROCESSING_MODE` must be `api` or `sdk`.

> Not required in this mode: `VLM_MODEL_NAME`, `ENABLED_WHISPER_MODELS`,
> `OD_MODEL_NAME`, `OVMS_LLM_MODEL_NAME`.

## URLs after deploy

- Search UI: `http://<HOST_IP>:<APP_HOST_PORT>/`
- Pipeline Manager: `http://<HOST_IP>:<APP_HOST_PORT>/manager/docs`
- Data Prep: `http://<HOST_IP>:7890/docs`
- Embedding server: `http://<HOST_IP>:9777/docs`

## API entry points (for follow-on search workflows)

1. `POST /manager/videos` — upload a video
2. `POST /manager/videos/search-embeddings/{videoId}` — generate embeddings
3. `POST /manager/search/query` — run a natural-language query
4. `GET  /manager/search/{queryId}` — fetch results
