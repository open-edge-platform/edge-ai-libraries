---
name: vdms-dataprep-dev
description: >
  Develop the VDMS DataPrep microservice itself — build images the sanctioned
  way (./build.sh with its microservices/-level context), run the pytest suite
  with coverage, lint, and navigate the SDK/API embedding
  pipeline. Use when modifying, testing, or debugging this service's code. Not
  for merely deploying the stack or ingesting videos — that is
  vdms-dataprep-user.
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
- Run the pytest suite with coverage, or lint
- Navigate/modify the SDK-or-API embedding pipeline and endpoints
- Debug the path dependency, fixed collection wiring, or MinIO endpoints

## Example Prompts

Sample Problem-solving scenarios this skill handles end-to-end:

| Example | Problem it solves |
|---|---|
| [onboard-embedding-model.md](./example-prompts/onboard-embedding-model.md) | Onboard a new embedding model into the ingestion pipeline |
| [update-test-cases.md](./example-prompts/update-test-cases.md) | Update test cases and inspect coverage |

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
poetry install --with dev         # Python >=3.11,<3.14; CPU wheels are base dependencies
```

`setup.sh` is **sourced** and (except for `--down`/`--build*`) requires
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` exported; ingestion also needs
`EMBEDDING_MODEL_NAME`.

## Test / lint loop

```bash
poetry run coverage run --rcfile ./pyproject.toml -m pytest tests
poetry run coverage report -m
poetry run coverage run --rcfile ./pyproject.toml -m pytest tests/test_db.py
poetry run black --check src tests && poetry run isort --check-only src tests
```

The suite (13 files, `conftest.py` with a `TestClient` and mocked MinIO) runs
offline. `setup.sh` currently has no test/lint subcommands, so use the direct
Poetry commands above. Details:
[`references/testing-and-build.md`](./references/testing-and-build.md).

## Build-and-run loop

```bash
bash -c 'export MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32" \
  && source ./setup.sh'           # builds with ./build.sh, then starts detached compose
```

This checkout has no dev compose overlay or live-reload subcommand. Rebuild
after source changes; use `source ./setup.sh --nd` for foreground logs and
`source ./setup.sh --down` for teardown.

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
| `setup.sh` unconditionally exports `INDEX_NAME=video-rag` and compose maps it to `DB_COLLECTION` | `VS_INDEX_NAME` has no effect; change the source or override `INDEX_NAME` after sourcing `--nosetup` before Compose |
| Compose sets `MINIO_ENDPOINT=${MINIO_HOST}:9000` | use the container port for service-to-service traffic; host access uses port 6010 |
| YOLOX weights download at first startup into the `dataprep-yolox-models` volume | offline first run silently disables detection — don't chase it as a code bug |
| Reusing a VDMS collection after changing embedding model | `Dimensions mismatch` at insert; use a fresh collection in tests |
| Every new file needs the SPDX header | CI/license scans fail otherwise |
