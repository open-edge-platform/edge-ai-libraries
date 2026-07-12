<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Testing & builds — VDMS DataPrep

## Tests

```bash
source ./setup.sh test                        # scripts/tester.sh → coverage gate
source ./setup.sh test tests/test_db.py       # one file
# equivalent direct form:
FASTAPI_ENV=development poetry run coverage run --rcfile ./pyproject.toml -m pytest tests/test_db.py
poetry run coverage report -m                 # COVERAGE_REQ default 80 (export to override)
```

- 12 test files (~850 lines): endpoint tests (`test_get_videos.py`,
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
- Coverage sources are `src` and `tests` (`pyproject.toml`); the gate fails
  under **80%** — new code needs tests to keep the bar.

## Lint

```bash
source ./setup.sh lint        # black (line length 100) + isort (black profile), check-only
source ./setup.sh lint -a     # apply fixes
```

## Builds (all go through the `microservices/` context)

| Command | What it does |
|---|---|
| `./build.sh` | Build `${REGISTRY}vdms-dataprep:${TAG:-latest}` (target `prod`); `--push` publishes |
| `source ./setup.sh --build` | Same target via setup.sh |
| `source ./setup.sh --build-lint` | Image build that runs lint stage (fails on violations) |
| `source ./setup.sh --build-test` | Image build running pytest + coverage gate (`COVERAGE_REQ` build-arg) |
| `source ./setup.sh --build-report` | Coverage HTML server image (`scripts/reporter.sh`, port 8899) |
| `source ./setup.sh --conf` / `--conf-dev` | Print resolved compose config without starting |

Why not `docker build .` from here: the Dockerfile copies both
`visual-data-preparation-for-retrieval/vdms/` **and**
`multimodal-embedding-serving/` from the context root — only
`microservices/` contains both. `build.sh` passes `-f docker/Dockerfile`
with context `../../..` for you.

## Debugging a running dev stack

- `source ./setup.sh --dev` then `docker compose -f docker/compose.yaml -f
  docker/compose-dev.yaml logs -f vdms-dataprep` — uvicorn `--reload` picks up
  source edits from the bind mount.
- `curl -s localhost:6007/v1/dataprep/health` — SDK mode reports
  `sdk_client_status`, model, device.
- `curl -s 'localhost:6007/v1/dataprep/telemetry?limit=5'` — stage timings
  (decode/detect/embed/store) to localize slowdowns.
- VDMS state: `docker exec` into the `vdms-vector-db` container or probe TCP
  6020; MinIO console at `http://localhost:6011`.
