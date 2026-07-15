<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Testing & builds — VDMS DataPrep

## Tests

```bash
poetry install --with dev
poetry run coverage run --rcfile ./pyproject.toml -m pytest tests
poetry run coverage report -m
# one file:
poetry run coverage run --rcfile ./pyproject.toml -m pytest tests/test_db.py
```

If `poetry install --with dev` fails building a native dependency with
`Python.h: No such file or directory`, install the development headers for the
active Python version (plus a C/C++ build toolchain) and rerun the install.
Do not treat pytest results from the partially installed environment as a
valid suite run; missing optional imports such as `mobileclip` are then a
dependency-setup failure, not a test failure.

- 13 test files: endpoint tests (`test_get_videos.py`,
  `test_download_video.py`, `test_delete_video.py`), pipeline/metadata
  (`test_prep_data.py`, `test_metadata.py`, `test_db.py`,
  `test_telemetry.py`), security (`test_validation_security.py`,
  `test_logger_security.py`, `test_config_utils_security.py`,
  `test_simple_client_security.py`), utils (`test_util.py`).
- `tests/conftest.py` fixtures: `test_client` (`TestClient(app)` — importing
  `src.main` is safe, no model loads at import), `mock_minio_client`
  (`MagicMock(spec=MinioClient)`), temp `video_file`/`invalid_video_file`.
- Suite is offline: MinIO/VDMS/embedding calls are mocked. Keep new tests
  that way — spin up no containers in unit tests.
- Coverage sources are `src` and `tests` (`pyproject.toml`). The checkout does
  not currently define a `fail_under` threshold; report the measured value
  without inventing a gate.

## Lint

```bash
poetry run black --check src tests
poetry run isort --check-only src tests
# apply fixes:
poetry run black src tests && poetry run isort src tests
```

## Builds (all go through the `microservices/` context)

| Command | What it does |
|---|---|
| `./build.sh` | Build `${REGISTRY}vdms-dataprep:${TAG:-latest}` (target `prod`); `--push` publishes |
| `source ./setup.sh --build` | Same target via setup.sh |
| `source ./setup.sh --conf` | Print resolved compose config without starting |

Why not `docker build .` from here: the Dockerfile copies both
`visual-data-preparation-for-retrieval/vdms/` **and**
`multimodal-embedding-serving/` from the context root — only
`microservices/` contains both. `build.sh` passes `-f docker/Dockerfile`
with context `../../..` for you.

## Debugging a running dev stack

- `source ./setup.sh` builds the changed source and starts the stack; this
  checkout has no live-reload compose overlay.
- `docker compose -f docker/compose.yaml logs -f vdms-dataprep` follows logs.
- `curl -s localhost:6007/v1/dataprep/health` — SDK mode reports
  `sdk_client_status`, model, device.
- `curl -s 'localhost:6007/v1/dataprep/telemetry?limit=5'` — stage timings
  (decode/detect/embed/store) to localize slowdowns.
- VDMS state: `docker exec` into the `vdms-vector-db` container or probe TCP
  6020; MinIO console at `http://localhost:6011`.
