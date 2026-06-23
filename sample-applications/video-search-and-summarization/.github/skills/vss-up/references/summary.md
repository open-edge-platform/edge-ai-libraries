<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Mode: `--summary` (Video Summarization only)

Concise summaries of long-form videos / live streams using VLM + computer
vision + audio analysis. No search/embedding stack.

## Deploy

```bash
# must be sourced in the user's shell:
source setup.sh --summary
# dry-run (safe to run yourself):
bash -c 'source setup.sh --summary config'
```

## Required shell env vars

Common to all deploy modes:
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`RABBITMQ_USER`, `RABBITMQ_PASSWORD`.

Required because this is **not** `--search`:
- `VLM_MODEL_NAME` — vision-language model for captioning/summary.
- `ENABLED_WHISPER_MODELS` — audio transcription models.
- `OD_MODEL_NAME` — object-detection model.
- `OVMS_LLM_MODEL_NAME` — **only if** `ENABLE_OVMS_LLM_SUMMARY=true` or
  `ENABLE_OVMS_LLM_SUMMARY_GPU=true`.

`EMBEDDING_PROCESSING_MODE` must still be `api` or `sdk` (validated globally).

## URLs after deploy

- Summarization UI: `http://<HOST_IP>:<APP_HOST_PORT>/`
- Pipeline Manager: `http://<HOST_IP>:<APP_HOST_PORT>/manager/docs`

## API entry points (for follow-on summarize workflows)

- `POST /manager/summary` — start a summarization
- `GET  /manager/summary/{stateId}` — poll status/result
- `GET  /manager/summary/{stateId}/raw` — raw output
