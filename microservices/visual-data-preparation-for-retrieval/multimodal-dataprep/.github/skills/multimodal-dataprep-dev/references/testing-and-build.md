<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Testing and builds — Multimodal DataPrep

## Install and test

Use Python 3.11–3.13 and install the optional development group:

```bash
poetry install --with dev
poetry run python -m pytest tests
poetry run coverage run --rcfile ./pyproject.toml -m pytest tests
poetry run coverage report -m
```

Use `python -m pytest` (or coverage's `-m pytest`) so the repository root is on
the import path. A plain `poetry run pytest` can fail to import `src` in this
package-mode-disabled project.

For focused work:

```bash
poetry run python -m pytest tests/test_image_endpoints.py
poetry run python -m pytest tests/test_vectorstores.py tests/test_storage_backends.py
poetry run python -m pytest tests/test_metrics_manager.py
```

The current tree contains 24 `test_*.py` modules plus `conftest.py`. Coverage
tracks `src` and `tests`; no `fail_under` threshold is configured.

Most tests mock external systems. `tests/test_milvus_integration.py` is skipped
unless `MILVUS_IT_URI` points to a real Milvus server:

```bash
MILVUS_IT_URI=http://localhost:19530 \
  poetry run python -m pytest tests/test_milvus_integration.py
```

Do not claim a clean suite when collection fails. Capture the exact failing
test modules and traceback, distinguish collection errors from test failures,
and avoid attributing pre-existing failures to an unrelated change.

## Formatting

```bash
poetry run black --check src tests
poetry run isort --check-only src tests

# Apply mechanical fixes:
poetry run black src tests
poetry run isort src tests
```

Black and isort use a 100-character line length from `pyproject.toml`.

## Build

```bash
./build.sh
./build.sh --push
source ./setup.sh --build
source ./setup.sh --build registry.example.com/team/multimodal-dataprep:test
```

`build.sh` builds `${REGISTRY_URL}${PROJECT_NAME}multimodal-dataprep:${TAG}`
with target `prod`. It passes `microservices/` as the build context because the
Dockerfile copies this service and `multimodal-embedding-serving`. A direct
`docker build -f docker/Dockerfile .` uses the wrong context.

## Configure and run

```bash
export MINIO_ROOT_USER='<user>'
export MINIO_ROOT_PASSWORD='<strong-password>'
export EMBEDDING_MODEL_NAME='CLIP/clip-vit-b-32'
source ./setup.sh --nosetup

source ./setup.sh --conf
docker compose -f docker/compose.yaml up -d --build
docker compose -f docker/compose.yaml logs -f multimodal-dataprep
```

`source ./setup.sh` with no argument only exports defaults; it does not build or
start containers. `source ./setup.sh --nd` runs the default stack in the
foreground with `--build`, and `source ./setup.sh --down` tears it down.

Backend variants:

```bash
# Milvus vector DB + MinIO media storage
docker compose -f docker/compose-milvus.yaml up -d --build

# VDMS vector DB + local filesystem media storage
docker compose -f docker/compose.yaml \
  -f docker/compose.storage-local.yaml up -d --build
```

## Runtime checks

```bash
curl -fsS http://localhost:6007/v1/dataprep/health
curl -fsS 'http://localhost:6007/v1/dataprep/telemetry?limit=5'
docker compose -f docker/compose.yaml ps
curl -fsS http://localhost:6010/minio/health/live
```

Use `embedding_client_status` for model readiness. For dependency diagnosis,
inspect Compose health/logs and probe VDMS (`localhost:6020`) or Milvus
(`localhost:19530`) separately.
