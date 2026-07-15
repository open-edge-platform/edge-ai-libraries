<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Testing — Multimodal Embedding Serving

## What exists today

```bash
poetry run python -m unittest tests/test_path_security.py -v
# or: poetry run pytest tests/  (pytest runs unittest cases fine; no pytest.ini here)
```

`tests/test_path_security.py` covers the `/tmp/videoQnA` sandbox
(`src/utils/path_security.py`): filename validation, extension allowlists,
traversal rejection. That is the **entire** automated suite — model handlers,
wrapper, and routes have no unit tests.

## Smoke-testing changes (recommended for any behavior change)

Fast in-process check with a small model (downloads `CLIP/clip-vit-b-32` on
first run):

```bash
poetry run python examples/sdk_examples.py       # SDK path: handler + EmbeddingModel
```

Full server check:

```bash
export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32"
source setup.sh && docker compose -f docker/compose.yaml up -d --build
until curl -sf localhost:9777/health; do sleep 5; done
poetry run python examples/server_examples.py    # exercises the REST endpoints
docker compose -f docker/compose.yaml down
```

## Adding tests

- Follow the existing `unittest.TestCase` style in `tests/` (class per area,
  `test_*` methods); pytest also collects these.
- Keep unit tests offline: patch `download_image`, handler `load_model`, and
  anything touching huggingface.co. Loading a real model in a unit test makes
  the suite unusably slow.
- Good first targets when touching related code: the `/embeddings` input
  union validation (`TestClient(app)` with a mocked `embedding_model` global),
  `src/models/registry.py` lookup/registration, `segment_config` priority
  handling in `src/utils/decoder.py`.
- Test the **wrapper API** (`EmbeddingModel`) when changing it — it is the
  SDK contract consumed by vdms-dataprep.
