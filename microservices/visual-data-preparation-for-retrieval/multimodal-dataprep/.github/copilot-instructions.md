<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Multimodal DataPrep — AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents. Keep tool-specific
files such as `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules/multimodal-dataprep.mdc`
as short pointers to this file.

## What This Service Is

Multimodal DataPrep ingests videos, images, and text summaries for retrieval. It
extracts video frames, optionally creates YOLOX object crops, generates
multimodal embeddings in-process, and stores vectors plus metadata through a
pluggable VDMS or Milvus backend. Raw media uses MinIO or local storage. The
service handles ingestion only; search and query are separate concerns.
Prebuilt image: `intel/multimodal-dataprep:latest`. Deeper user docs live under
[`docs/user-guide/`](../docs/user-guide/); this file is the agent-facing map.

## The Stack

| Service | Image | Host port → container |
|---|---|---|
| multimodal-dataprep | `intel/multimodal-dataprep:latest` (or local build) | `6007` → 8000, API under `/v1/dataprep` |
| vdms-vector-db | `intellabs/vdms:v2.12.0` | `6020` → 55555 |
| milvus-standalone | Milvus | `19530` → 19530 when that backend is selected |
| minio-server | MinIO | `6010` → 9000 (API), `6011` → 9001 (console) |

Embedding runs in-process through the multimodal embedding package. Select the
vector database with `MM_DATAPREP_VECTORDB_BACKEND` (`vdms` or `milvus`) and
the storage backend with `MM_DATAPREP_STORAGE_BACKEND` (`minio` or `local`).

## Run Interfaces

- `setup.sh` must be **sourced**, never executed. It requires
  `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` (any strong values — never commit
  them) and `EMBEDDING_MODEL_NAME` (e.g. `CLIP/clip-vit-b-32`) exported first.
- Bare `source ./setup.sh` **builds from source** via `./build.sh`, then
  `docker compose -f docker/compose.yaml up -d --no-build`.
- Subcommands: `--nd` (foreground), `--down`, `--conf` (print resolved
  compose), and `--build [tag]`. Tests and lint run directly through Poetry;
  `setup.sh` has no test/lint or dev-overlay subcommands in this checkout.
- **Never `docker build` from this directory** — the build context is
  `microservices/` (three levels up) because of the
  `../../multimodal-embedding-serving` path dependency. Always use
  `./build.sh`.

## API Surface (prefix `/v1/dataprep`, e.g. `http://localhost:6007/v1/dataprep/health`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service and embedding-pipeline status |
| POST | `/media/upload` | Upload and embed one video or image |
| POST | `/media/process` | Process media already in object storage |
| POST | `/media/ingest` | Ingest a base64 image or remote image URL |
| POST | `/media/*/batch`, `/media/ingest-dir` | Start asynchronous batch ingestion |
| GET | `/media/jobs/{job_id}` | Poll a batch job |
| POST | `/summary` | Embed a text summary with a video time range |
| POST | `/media/rtsp` | Ingest an RTSP stream |
| GET | `/media` | List stored media |
| GET | `/media/download` | Download or stream stored media |
| DELETE | `/media/{bucket_name}/{video_id}` | Delete stored media |
| GET | `/telemetry` | Recent ingestion telemetry |

## Repository Map

| Path | Contents |
|---|---|
| `setup.sh` / `setup-with-embedding.sh` | Env + lifecycle entrypoints (source them). |
| `build.sh` | The only sanctioned image build (context = `microservices/`). |
| `docker/` | `compose.yaml` (sdk), `compose-with-embedding.yaml` (api), `Dockerfile`. |
| `src/main.py` | FastAPI app (`root_path=/v1/dataprep`); lifespan preloads SDK client + YOLOX, flushes the VDMS index on shutdown. |
| `src/endpoints/` | One router package per API area. |
| `src/core/embedding/` | The pipeline: `sdk_embedding_helper.py` (SDK mode), `simple_client.py` (api mode), `sdk_client.py` (VDMS writes via langchain-vdms), `decoder.py` (frame extraction). |
| `src/core/object_detection/` | YOLOX detector + utils. |
| `src/core/minio_client.py`, `src/common/settings.py` | Object storage client; pydantic Settings. |
| `scripts/` | Container entrypoint and runtime helpers. |
| `tests/` | 12 pytest files + `conftest.py` (mocked MinIO, TestClient). |

## Conventions

- Run commands from this microservice's root unless a skill says otherwise.
- **Credentials are never committed** — export MinIO creds in-shell.
- Every new source/config/doc file carries the repo SPDX header
  (`SPDX-FileCopyrightText: (C) 2026 Intel Corporation` / `Apache-2.0`).
- Probe `GET http://localhost:6007/v1/dataprep/health` before API workflows.
- Destructive operations (wiping the VDMS collection, deleting volumes or
  bucket contents) need explicit user confirmation.

## Gotchas

- **VDMS dimension mismatch**: reusing a `DB_COLLECTION` created with a
  different embedding model throws "Dimensions mismatch" — fix is destructive
  (new collection name or wipe), so confirm first.
- **YOLOX downloads on first run** — without network, object detection is
  **silently disabled**.
- `setup.sh` exports `INDEX_NAME=video-rag`; compose maps it to
  `DB_COLLECTION`.
- Volumes `dataprep-yolox-models`, `ov-models`, `data-prep` hold model/scratch
  state; MinIO persists to the named Docker volume `MM_minio_data`.
- A 413 may come from an upstream proxy/server; the source upload endpoint has
  no implemented size check and buffers the full body. Stage large files in
  MinIO and use `POST /videos/minio`.
- Video and common image formats are supported for embedding creation.

## Skills

Reusable workflow skills live under [`.github/skills/`](skills/). Use
[`skill-catalog.json`](skills/skill-catalog.json) to pick the relevant skill,
then read that skill's `SKILL.md`.

| User intent | Skill |
|---|---|
| Bring up the stack and ingest/manage videos from an app | `multimodal-dataprep-user` |
| Build from source, run tests/lint, modify the pipeline | `multimodal-dataprep-dev` |

## Skill Loading Rules

- Load only the skill needed for the current request.
- Open a skill's linked docs or `references/` files only when its `SKILL.md`
  points to them.
- Run commands yourself when the harness permits it and relay the result.

## Path Conventions

All paths in the skill catalog are relative to this microservice's root
(`microservices/visual-data-preparation-for-retrieval/multimodal-dataprep/`). The skills live
in `.github/skills` as the shared location for Codex, Copilot CLI, Claude
Code, Cursor, and local agent scripts. Skills also work without a repo clone —
the `-user` skill fetches the same `setup.sh`/compose files and docs from
GitHub and uses the prebuilt images.
