---
name: multimodal-embedding-serving-dev
description: >
  Develop the Multimodal Embedding Serving microservice itself — Poetry
  install, run the existing tests, navigate the wrapper/registry/handler
  architecture, add a new model family, and build the image from source. Use
  when modifying, testing, or debugging this service's code. Not for merely
  deploying or calling the API — that is multimodal-embedding-serving-user.
---

# Multimodal Embedding Serving — Dev

Work on the service's source. **This skill assumes a repo clone** of
`edge-ai-libraries` with this microservice at
`microservices/multimodal-embedding-serving/`; if there is no clone, clone the
repo first (`git clone
https://github.com/open-edge-platform/edge-ai-libraries.git -b release-2026.2.0`) or — if the user
only wants to *use* the service — switch to
[`../multimodal-embedding-serving-user/SKILL.md`](../multimodal-embedding-serving-user/SKILL.md).
Run all commands from the microservice root.

## When to Use

- Add or modify a model-family handler (CLIP/SigLIP/MobileCLIP/CN-CLIP/Blip2/QwenText)
- Run or extend the existing test suite
- Navigate the wrapper → registry → handler architecture before editing
- Build the image from source
- Debug model load, OpenVINO conversion, or import failures

## Example Prompts

Sample Problem-solving scenarios this skill handles end-to-end:

| Example | Problem it solves |
|---|---|
| [onboard-new-model.md](./example-prompts/onboard-new-model.md) | Onboard a new embedding model family (REST + SDK) |
| [update-test-cases.md](./example-prompts/update-test-cases.md) | Update test cases to cover a newly onboarded model |

## Reference Lookup

| File | Load when… |
|---|---|
| [`references/source-map.md`](./references/source-map.md) | locating code before editing, or adding a model family (checklist inside) |
| [`references/testing.md`](./references/testing.md) | running/adding tests or smoke-testing changes |

## Environment setup

```bash
poetry install    # Python >=3.10,<3.14
```

**Known limitation:** `mobileclip` and `salesforce-lavis` are installed only
in the Docker image (see `docker/Dockerfile`), not via `pyproject.toml`. In a
bare Poetry env, MobileCLIP and Blip2 handlers fail to import — develop those
families against the container:

```bash
export EMBEDDING_MODEL_NAME="MobileCLIP/mobileclip_s0"
source setup.sh && docker compose -f docker/compose.yaml up -d --build
```

## Architecture in one paragraph

`src/app.py` (routes, input union) → `src/wrapper.py` (`EmbeddingModel`, the
high-level API — also the **SDK surface**) → `src/models/registry.py`
(factory) → `src/models/handlers/<family>_handler.py` (per-family
`load_model`/`encode_text`/`encode_image`, PyTorch and optional OpenVINO
paths). `src/models/config.py` holds the 19-model registry. Map + add-a-model
checklist: [`references/source-map.md`](./references/source-map.md).

## Test / verify loop

```bash
poetry run python -m unittest tests/test_path_security.py -v   # the existing suite
```

Coverage is thin (path security only) — for behavior changes, smoke-test via
`examples/server_examples.py` / `examples/sdk_examples.py` against a small
CLIP model: [`references/testing.md`](./references/testing.md).

## Build from source

```bash
export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32"
source setup.sh                                   # sourced; hard-fails without the model name
docker compose -f docker/compose.yaml build
docker compose -f docker/compose.yaml up -d
```

## Debug a running instance

1. `docker logs -f multimodal-embedding-serving` — model load, conversion,
   request logs (server runs `--log-level debug`).
2. `curl -s localhost:9777/model/current` and `/model/capabilities` — ground
   truth for what's loaded.
3. Slow first inference = lazy OpenVINO export/compile into
   `EMBEDDING_OV_MODELS_DIR` (`/app/ov_models`); cached afterwards in the
   `ov-models` volume.

## Contribution gotchas

| Gotcha | Consequence |
|---|---|
| `src/wrapper.py` is a **path dependency of multimodal-dataprep** (`visual-data-preparation-for-retrieval/multimodal-dataprep`) | API changes there ripple into that service — check its usage before changing signatures |
| Package is built as a wheel (`poetry build`; `packages` maps `src/` → `multimodal_embedding_serving`) | keep new modules importable under the package name; SDK users import from it |
| `INFER_BATCH_SIZE` compiles OpenVINO models to a fixed batch shape | handler changes must keep the pad/split logic intact |
| QwenText handlers are text-only by design | don't "fix" the 400 for images; capability flags live on the handler |
| Every new file needs the SPDX header | CI/license scans fail otherwise |
