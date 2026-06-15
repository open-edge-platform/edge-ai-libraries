<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Mode: `--summary --search` → Dual (two separate UIs)

Summarization and search running side by side with **independent** UI
instances. `setup.sh` aliases `--summary --search` (either order) to `--dual`.

## Deploy

```bash
source setup.sh --summary --search      # aliased to --dual
bash -c 'source setup.sh --dual config' # dry-run
```

## Required shell env vars

Common to all deploy modes:
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`RABBITMQ_USER`, `RABBITMQ_PASSWORD`.

Summary side (mode is not `--search`):
- `VLM_MODEL_NAME`, `ENABLED_WHISPER_MODELS`, `OD_MODEL_NAME`
- `OVMS_LLM_MODEL_NAME` — only if `ENABLE_OVMS_LLM_SUMMARY[_GPU]=true`

Search side (`--dual` requires it):
- `MULTIMODAL_EMBEDDING_MODEL`

`EMBEDDING_PROCESSING_MODE` must be `api` or `sdk`.

This is the **superset** of `--summary` and `--search` requirements.

## URLs after deploy (two UIs)

- Summarization UI: `http://<HOST_IP>:<APP_HOST_PORT>/summary/`
- Search UI: `http://<HOST_IP>:<APP_HOST_PORT>/search/`
- Root `…/` redirects to the Summary UI.
- Pipeline Manager: `…/manager/docs`; Data Prep `:7890/docs`; Embedding `:9777/docs`.
