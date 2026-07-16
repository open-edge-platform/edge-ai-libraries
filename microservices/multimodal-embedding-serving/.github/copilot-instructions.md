<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Multimodal Embedding Serving — AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents. Keep tool-specific
files such as `AGENTS.md`, `CLAUDE.md`, and
`.cursor/rules/multimodal-embedding-serving.mdc` as short pointers to this
file.

## What This Service Is

Multimodal Embedding Serving generates embeddings for **text, images, and
videos** in a shared semantic space (FastAPI + PyTorch/OpenVINO). It is
consumable two ways: as a **REST service** (prebuilt
`intel/multimodal-embedding-serving:latest` on Docker Hub, port 9777) and as a
**Python SDK wheel** (`multimodal_embedding_serving`, built with
`poetry build`) for in-process use. Deeper user docs live under
[`docs/user-guide/`](../docs/user-guide/); this file is the agent-facing map.

## Run Interfaces

- `setup.sh` must be **sourced**, never executed. It **hard-fails
  (`return 1`) unless `EMBEDDING_MODEL_NAME` is exported first** (e.g.
  `CLIP/clip-vit-b-32`). It creates the external volumes `ov-models` and
  `data-prep`.
- Deploy: `export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32" && source setup.sh
  && docker compose -f docker/compose.yaml up -d`. Host port
  `EMBEDDING_SERVER_PORT` (**9777**, hardcoded by setup.sh) maps to container
  8000.
- Models download and (optionally) convert to OpenVINO lazily at startup;
  `EMBEDDING_DEVICE=GPU` auto-enables `EMBEDDING_USE_OV=true` + THROUGHPUT
  mode in setup.sh.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/embeddings` | Embed text / image / video (typed `input` union) |
| GET | `/models` | All available model ids by family |
| GET | `/model/current` | Loaded model + device + OpenVINO flag |
| GET | `/model/capabilities` | Modalities the loaded model supports |
| GET | `/health` | 200 healthy / 500 unhealthy |

## Model Families

CLIP (×4), CN-CLIP (×3, Chinese+English), MobileCLIP (×5), SigLIP (×3),
Blip2 (`Blip2/blip2_transformers`), QwenText (×3, `Qwen/Qwen3-Embedding-*`,
**text-only**). Model ids are `Family/name`, e.g. `CLIP/clip-vit-b-16`. Always
check `GET /model/capabilities` before sending non-text inputs.

## Repository Map

| Path | Contents |
|---|---|
| `setup.sh` | Env export + volume creation (source it; needs `EMBEDDING_MODEL_NAME`). |
| `docker/` | `compose.yaml` + `Dockerfile`. |
| `src/app.py` | FastAPI routes + request models (input union). |
| `src/wrapper.py` | `EmbeddingModel` — the high-level embed API (also the SDK surface). |
| `src/models/` | `config.py` (registry of 19 models), `registry.py` (factory), `base.py` (ABC), `handlers/` (one per family). |
| `src/utils/` | Settings, downloads/SSRF checks, video decoder, path security. |
| `examples/` | `sdk_examples.py`, `server_examples.py`. |
| `tests/` | `test_path_security.py` (unittest). |
| `docs/user-guide/` | get-started, api-reference, supported-models, sdk-usage, wheel-installation. |

## Tech Stack

Python 3.10+ with Poetry (packaged — `poetry build` yields the SDK wheel),
FastAPI + Gunicorn, open_clip / cn_clip / transformers / optimum-intel,
OpenVINO optional per model.

## Conventions

- Run commands from this microservice's root unless a skill says otherwise.
- `setup.sh` is **sourced**, never executed directly.
- Every new source/config/doc file carries the repo SPDX header
  (`SPDX-FileCopyrightText: (C) 2026 Intel Corporation` / `Apache-2.0`).
- Probe `GET http://localhost:9777/health` before any API workflow.
- Destructive operations (removing `ov-models`/`data-prep` volumes) need
  explicit user confirmation.

## Gotchas

- QwenText models reject image/video inputs (400) — capability-check first.
- `mobileclip` and `salesforce-lavis` are installed **only in the Docker
  image** (not in `pyproject.toml`); MobileCLIP/BLIP2 families can't run in a
  bare Poetry env.
- `INFER_BATCH_SIZE` compiles OpenVINO models to a **fixed batch shape**.
- `video_file`/`frames_batch` inputs accept bare filenames only, resolved
  under the container's `/tmp/videoQnA` sandbox.
- This package is a **path dependency of the VDMS DataPrep microservice**
  (`visual-data-preparation-for-retrieval/vdms`) — changes to
  `src/wrapper.py`'s API ripple there.

## Skills

Reusable workflow skills live under [`.github/skills/`](skills/). Use
[`skill-catalog.json`](skills/skill-catalog.json) to pick the relevant skill,
then read that skill's `SKILL.md`.

| User intent | Skill |
|---|---|
| Deploy the service or embed content from an app (REST or SDK) | `multimodal-embedding-serving-user` |
| Build from source, run tests, add model handlers | `multimodal-embedding-serving-dev` |

## Skill Loading Rules

- Load only the skill needed for the current request.
- Open a skill's linked docs or `references/` files only when its `SKILL.md`
  points to them.
- Run commands yourself when the harness permits it and relay the result.

## Path Conventions

All paths in the skill catalog are relative to this microservice's root
(`microservices/multimodal-embedding-serving/`). The skills live in
`.github/skills` as the shared location for Codex, Copilot CLI, Claude Code,
Cursor, and local agent scripts. Skills also work without a repo clone — the
`-user` skill fetches the same `setup.sh`/compose files and docs from GitHub
and uses the prebuilt image.
