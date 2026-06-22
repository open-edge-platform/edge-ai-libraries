<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Mode: `--summary-and-search` → Unified (single UI, search over summaries)

A modified Video Search application that **summarizes first, then searches over
the summary content** — one unified UI. `setup.sh` aliases
`--summary-and-search` (and `--all`, `--search-and-summary`) to `--unified`.

## Deploy

```bash
source setup.sh --summary-and-search       # aliased to --unified
bash -c 'source setup.sh --unified config' # dry-run
```

## Required shell env vars

Common to all deploy modes:
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`RABBITMQ_USER`, `RABBITMQ_PASSWORD`.

Summary stack (mode is not `--search`):
- `VLM_MODEL_NAME`, `ENABLED_WHISPER_MODELS`, `OD_MODEL_NAME`
- `OVMS_LLM_MODEL_NAME` — only if `ENABLE_OVMS_LLM_SUMMARY[_GPU]=true`

Unified-only:
- `TEXT_EMBEDDING_MODEL` — dedicated text-embedding model for searching over the
  generated summary text (enforced only in `--unified`).

`EMBEDDING_PROCESSING_MODE` must be `api` or `sdk`.

> Note: `MULTIMODAL_EMBEDDING_MODEL` is enforced for `--search`/`--dual`, not
> `--unified`; unified searches over summary **text** via `TEXT_EMBEDDING_MODEL`.

## URLs after deploy (single UI)

- Unified UI: `http://<HOST_IP>:<APP_HOST_PORT>/`
- Pipeline Manager: `…/manager/docs`; Data Prep `:7890/docs`; Embedding `:9777/docs`.
