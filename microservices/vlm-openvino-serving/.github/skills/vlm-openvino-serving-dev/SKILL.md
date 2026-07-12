---
name: vlm-openvino-serving-dev
description: >
  Develop the VLM OpenVINO Serving microservice itself — Poetry install, run
  the mocked pytest suite safely (model loads at import time), navigate
  src/app.py and the per-model dispatch, build the image from source, and
  debug via logs and telemetry. Use when modifying, testing, or debugging this
  service's code. Not for merely deploying or calling the API — that is
  vlm-openvino-serving-user.
---

# VLM OpenVINO Serving — Dev

Work on the service's source. **This skill assumes a repo clone** of
`edge-ai-libraries` with this microservice at
`microservices/vlm-openvino-serving/`; if there is no clone, clone the repo
first (`git clone https://github.com/open-edge-platform/edge-ai-libraries.git`)
or — if the user only wants to *use* the service — switch to
[`../vlm-openvino-serving-user/SKILL.md`](../vlm-openvino-serving-user/SKILL.md).
Run all commands from the microservice root.

## When to Use

- Add or modify a per-model prompt/dispatch branch in `src/app.py`
- Run or extend the mocked pytest suite (safe against the import-time model load)
- Navigate routes, model lifecycle, or conversion helpers before editing
- Build the image from source
- Debug startup, GPU OOM self-restart, or missing telemetry

## Example Prompts

Sample Problem-solving scenarios this skill handles end-to-end:

| Example | Problem it solves |
|---|---|
| [onboard-new-model.md](./example-prompts/onboard-new-model.md) | Onboard a new VLM family (dispatch + config + capabilities) |
| [update-test-cases.md](./example-prompts/update-test-cases.md) | Update the mocked test suite to cover a new model |

## Reference Lookup

| File | Load when… |
|---|---|
| [`references/source-map.md`](./references/source-map.md) | locating where a route, model branch, or utility lives before editing |
| [`references/testing.md`](./references/testing.md) | writing new tests, running subsets, or debugging test failures/hangs |

## The one gotcha to know first

`src/app.py` calls `initialize_model()` **at import time** — importing it
without mocks downloads and converts a multi-GB model. The test suite mocks
this; never run a bare `python -c "import src.app"` or an unmocked pytest
collection against real settings. Details:
[`references/testing.md`](./references/testing.md).

## Environment setup

```bash
poetry install --with test    # Python ^3.11,<3.14
```

## Test / verify loop

```bash
cd tests && poetry run pytest            # pytest.ini lives in tests/
poetry run coverage run --source=src -m pytest && poetry run coverage report
```

~50 tests, all model interactions mocked (no downloads, CPU-only, fast).

## Source map (summary)

- `src/app.py` (~1600 lines) — **everything routes through here**: FastAPI
  routes, model lifecycle, per-model prompt branches (Qwen / Phi / SmolVLM /
  default, dispatched by substring on the model name), streaming, GPU-OOM
  self-restart.
- `src/utils/` — `common.py` (pydantic Settings, error strings), `utils.py`
  (model conversion, image/video loading), `data_models.py` (request/response
  schemas), `telemetry*.py`.
- `src/config/model_config.yaml` — per-model pixel limits + the
  `video_supported_models` list.
- Full annotated map: [`references/source-map.md`](./references/source-map.md).

## Build from source

```bash
export VLM_MODEL_NAME="Qwen/Qwen2.5-VL-3B-Instruct"
source setup.sh                                   # sourced, never executed
docker compose -f docker/compose.yaml build       # image ${REGISTRY:-}vlm-openvino-serving:${TAG:-latest}
docker compose -f docker/compose.yaml up -d
```

Model export/compression at container start is `scripts/compress_model.sh`
(`optimum-cli export openvino`); it skips work if the model dir already exists
in the `ov-models` volume.

## Debug a running instance

1. `docker logs -f vlm-openvino-serving` — startup, conversion, request logs.
2. `curl -s localhost:9764/health` (503 = model not ready) and
   `curl -s localhost:9764/v1/queue-status`.
3. `curl -s 'localhost:9764/v1/telemetry?limit=5'` — per-request perf metrics
   (absent for SmolVLM).
4. More logs: `export VLM_LOG_LEVEL=debug` before `source setup.sh` (also
   raises the OpenVINO log level), then recreate the container.

## Contribution gotchas

| Gotcha | Consequence |
|---|---|
| Model dispatch is substring-based (`qwen2`, `phi-3.5-vision`, `smolvlm` in `src/utils/common.py`) | new model families need a dispatch branch + `model_config.yaml` entry |
| `VLM_DEVICE=GPU` forces int4 + 1 worker in `setup.sh` | keep that invariant when touching setup/compose |
| GPU OOM (`error code: -5`) triggers `os.execv` self-restart in `app.py` | don't "fix" restarts away; it's deliberate recovery |
| SmolVLM uses optimum-intel, not openvino_genai | no PerfMetrics → no telemetry for it; guard telemetry code paths |
| Every new file needs the SPDX header | CI/license scans fail otherwise |
