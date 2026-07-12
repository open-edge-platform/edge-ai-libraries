---
name: vdms-dataprep-dev
description: >
  Develop the VDMS DataPrep microservice itself — build images the sanctioned
  way (./build.sh with its microservices/-level context), run the pytest suite
  with the 80% coverage gate, lint, use the dev compose overlay with live
  reload, and navigate the SDK/API embedding pipeline. Use when modifying,
  testing, or debugging this service's code. Not for merely deploying the stack
  or ingesting videos — that is vdms-dataprep-user.
---

# VDMS DataPrep — Dev

Work on the service's source. **This skill assumes a repo clone** of
`edge-ai-libraries` with this microservice at
`microservices/visual-data-preparation-for-retrieval/vdms/`; if there is no
clone, clone the repo first (`git clone
https://github.com/open-edge-platform/edge-ai-libraries.git`) or — if the user
only wants to *use* the stack — switch to
[`../vdms-dataprep-user/SKILL.md`](../vdms-dataprep-user/SKILL.md). Run all
commands from the microservice root.

## When to Use

- Build the image the sanctioned way (`./build.sh`, `microservices/` context)
- Run the pytest suite with the 80% coverage gate, or lint
- Use the dev compose overlay with live reload
- Navigate/modify the SDK-or-API embedding pipeline and endpoints
- Debug the path dependency, `VS_INDEX_NAME` wiring, or MinIO endpoints

## Example Prompts

Sample Problem-solving scenarios this skill handles end-to-end:

| Example | Problem it solves |
|---|---|
| [onboard-embedding-model.md](./example-prompts/onboard-embedding-model.md) | Onboard a new embedding model into the ingestion pipeline |
| [update-test-cases.md](./example-prompts/update-test-cases.md) | Update test cases and keep the 80% coverage gate green |

## Reference Lookup

| File | Load when… |
|---|---|
| [`references/source-map.md`](./references/source-map.md) | locating pipeline/endpoint code before editing |
| [`references/testing-and-build.md`](./references/testing-and-build.md) | test/lint/coverage details, build targets, or build failures |

## The one rule to know first

**Never `docker build` from this directory.** The image depends on the sibling
`../../multimodal-embedding-serving` package, so the build context is
`microservices/` (three levels up). `./build.sh` handles that; a direct build
fails on the path dependency.

## Environment setup

```bash
poetry install --with dev,cpu     # Python >=3.10,<3.14; cpu group pins torch-cpu
```

`setup.sh` is **sourced** and (except for `--down`/`--build*`) requires
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` exported; ingestion also needs
`EMBEDDING_MODEL_NAME`.

## Test / lint loop

```bash
source ./setup.sh test                       # full suite + coverage gate (fails under 80%)
source ./setup.sh test tests/test_db.py      # single file
source ./setup.sh lint                       # black + isort check (add -a to apply)
```

The suite (12 files, `conftest.py` with a `TestClient` and mocked MinIO) runs
offline. Details and Docker-gated variants (`--build-test`, `--build-lint`,
`--build-report`):
[`references/testing-and-build.md`](./references/testing-and-build.md).

## Dev loop with live reload

```bash
bash -c 'export MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32" \
  && source ./setup.sh --dev'     # compose.yaml + compose-dev.yaml: mounts source, uvicorn --reload
```

Uses collection `video-rag-dev`; `--dev --nd` for foreground. Prod-style run:
bare `source ./setup.sh` (builds via `./build.sh`, then detached compose).
Teardown: `source ./setup.sh --down`.

## Architecture in one paragraph

`src/main.py` (FastAPI, `root_path=/v1/dataprep`; lifespan preloads the SDK
embedding client + YOLOX detector, flushes the VDMS index on shutdown) →
`src/endpoints/<area>/` routers → `src/core/embedding/`
(`simplified_embedding_helper.py` orchestrates; `sdk_embedding_helper.py` is
the in-process pipeline: decode → detect → embed → store;
`simple_client.py` is the HTTP alternative for `api` mode; `sdk_client.py`
writes to VDMS via langchain-vdms) with `src/core/object_detection/` (YOLOX)
and `src/core/minio_client.py`. Full map:
[`references/source-map.md`](./references/source-map.md).

## Contribution gotchas

| Gotcha | Consequence |
|---|---|
| Path dependency on `../../multimodal-embedding-serving` | its `EmbeddingModel` API is your contract; coordinate changes across both services |
| `docker/compose.yaml` reads `DB_COLLECTION` from `VS_INDEX_NAME` but `setup.sh` exports `INDEX_NAME` | without `VS_INDEX_NAME`, prod compose silently uses the code default `video-rag-test` (`src/common/settings.py`) |
| Repo compose sets `MINIO_ENDPOINT` from the **host** port (`${MINIO_HOST}:${MINIO_API_HOST_PORT:-4001}`) | container-internal MinIO listens on 9000 — `compose-with-embedding.yaml` hardcodes `:9000`; keep endpoint wiring consistent when touching compose |
| YOLOX weights download at first startup into the `vdms-yolox-models` volume | offline first run silently disables detection — don't chase it as a code bug |
| Reusing a VDMS collection after changing embedding model | `Dimensions mismatch` at insert; use a fresh collection in tests |
| Every new file needs the SPDX header | CI/license scans fail otherwise |
