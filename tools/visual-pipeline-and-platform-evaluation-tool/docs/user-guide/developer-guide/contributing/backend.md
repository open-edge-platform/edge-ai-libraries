# Backend

The ViPPET backend lives in [`vippet/`](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/tools/visual-pipeline-and-platform-evaluation-tool/vippet).
It is a Python 3.12 / FastAPI service that exposes a REST API on port `7860`,
orchestrates GStreamer + DL Streamer pipelines as subprocesses, runs
benchmarks, and proxies model installation to the `model-download`
microservice.

This page covers what a contributor needs in order to navigate the code,
run it locally, follow the conventions, and validate changes before opening
a pull request. For an end-to-end architectural overview see
[ViPPET Backend](../architecture/vippet-be.md).

## Source layout

```text
vippet/
├── api/                  # FastAPI app
│   ├── main.py           # App entrypoint, router registration, middleware
│   ├── api_schemas.py    # Pydantic v2 request/response models
│   ├── middleware.py     # Custom middleware (e.g., upload size limits)
│   ├── routes/           # Route handlers, one module per resource
│   │   ├── pipelines.py
│   │   ├── pipeline_templates.py
│   │   ├── models.py
│   │   ├── jobs.py
│   │   ├── cameras.py
│   │   ├── videos.py
│   │   ├── images.py
│   │   ├── devices.py
│   │   ├── convert.py
│   │   ├── tests.py
│   │   └── health.py
│   └── static/           # Static assets served by the API
├── managers/             # Business logic; thread-safe singletons
│   ├── pipeline_manager.py
│   ├── pipeline_template_manager.py
│   ├── camera_manager.py
│   ├── model_manager.py
│   ├── metadata_manager.py
│   ├── optimization_manager.py
│   ├── validation_manager.py
│   ├── app_state_manager.py
│   └── tests_manager.py
├── pipelines/            # Built-in GStreamer pipeline YAMLs + loader
├── graph.py              # In-memory pipeline graph (parse / serialize / simple view)
├── pipeline_runner.py    # Subprocess-based pipeline executor
├── gst_runner.py         # Low-level GStreamer runner (invoked as subprocess)
├── benchmark.py          # Density benchmarking
├── video_encoder.py      # Encoding / live-streaming sub-pipelines
├── video_decoder.py      # Decoder selection / caps building
├── device.py             # OpenVINO device detection (CPU/GPU/NPU)
├── camera.py             # Camera enumeration helpers
├── videos.py             # Input/output video management
├── images.py             # Image set management
├── models.py             # Supported models catalog
├── resources.py          # Shared resource managers (labels, scripts, model-procs)
├── utils.py              # Generic helpers (ids, timestamps, slugify, ...)
├── internal_types.py     # Internal dataclasses used between managers
├── requirements.txt      # Production dependencies
├── requirements-dev.txt  # Dev / test dependencies
├── tests/                # unittest + pytest suites
└── Dockerfile            # Multi-stage image (prod / test targets)
```

A few invariants worth knowing:

- Managers (`PipelineManager`, `CameraManager`, etc.) are thread-safe singletons.
  Create them with `Manager()`, do not pass instances around.
- The `vippet/` package uses **relative imports** and is meant to be run from
  the container context (`PYTHONPATH=/app`). Tests run inside the same image.
- GStreamer pipelines are **not** executed in-process. `pipeline_runner.py`
  builds a command line and starts `gst_runner.py` as a subprocess.
- OpenVINO™ device detection (`device.py`) happens at startup and drives
  which hardware profile (`cpu`, `gpu`, `npu`) is selected at compose time.

## Tech stack

| Layer            | Technology                                          |
| ---------------- | --------------------------------------------------- |
| Language         | Python 3.12                                         |
| Web framework    | FastAPI + uvicorn                                   |
| Validation       | Pydantic v2                                         |
| AI inference     | OpenVINO™ 2025.x, DL Streamer 2026.x, GStreamer 1.0 |
| Metrics          | Telegraf, qmassa (GPU), InfluxDB line protocol      |
| Containerization | Docker Compose (profiles: `cpu`, `gpu`, `npu`)      |
| Lint / type      | ruff, pyright (strict)                              |
| Tests            | unittest + coverage (unit), pytest (functional)     |

## Local development loop

The recommended workflow uses Docker Compose with the dev override, which
mounts the source tree into the running container and disables the health
check so you can iterate without rebuilding the image:

```bash
./setup_env.sh        # auto-detect CPU/GPU/NPU, write .env
make env-setup        # create shared/ subdirectories
make build-dev        # build images with target=dev
make run-dev          # start all services with compose.dev.yml overlay
make shell-vippet     # exec into the vippet container
```

Useful targets while iterating:

| Target                       | Description                                                 |
| ---------------------------- | ----------------------------------------------------------- |
| `make run-dev`               | Start the stack with live code reload.                      |
| `make stop`                  | Stop all compose services.                                  |
| `make clean`                 | Stop containers and remove generated volumes.               |
| `make shell-vippet`          | Open a shell in the `vippet` container.                     |
| `make shell-model-download`  | Shell in `model-download`.                                  |
| `make shell-metrics-manager` | Shell in `metrics-manager`.                                 |
| `make generate_openapi`      | Regenerate the OpenAPI schema after changing routes/models. |

The API is exposed at `http://localhost:7860/api/v1/` and the
auto-generated Swagger UI at `http://localhost:7860/docs`.

## Coding standards

Strictly follow the rules below, they are enforced by `ruff`, `pyright`
and code review.

### Python typing (Python 3.12+)

- Use built-in generics: `list`, `dict`, `set`, `tuple`.
- Use `|` for unions and `T | None` for optional values.
- Do **not** use `List`, `Dict`, `Union`, `Optional` from `typing`.
- Import from `typing` only when actually necessary
  (`Literal`, `Protocol`, `TypeVar`, ...).

```python
def process(data: list[dict[str, int]] | None) -> bool:
    return data is not None
```

### FastAPI routes

- Place every route in `vippet/api/routes/`, one module per resource.
- Use `async def` for handlers.
- Use Pydantic v2 models from `api_schemas.py` for both request bodies and
  responses; call `.model_dump()` (never the deprecated `.dict()`).
- Document each endpoint with a markdown docstring, Swagger renders it.
  See the example in [`AGENTS.md`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/tools/visual-pipeline-and-platform-evaluation-tool/AGENTS.md).
- Use `logging` (module-level logger), never `print()`.

### Managers and helpers

- Regular (non-API) docstrings follow Google / NumPy style, no markdown.
- Class names: `PascalCase`. Functions/variables: `snake_case`.
  Constants: `UPPER_SNAKE_CASE`. Private methods: `_leading_underscore`.
- Keep changes small and focused; do not bundle unrelated refactors.

### Logging

- Acquire a logger with `logging.getLogger(__name__)` (or a stable
  manager-specific name such as `"PipelineManager"`).
- Levels are configured by environment variables:
  `APP_LOG_LEVEL` (application), `RUNNER_LOG_LEVEL` (`gst_runner.py`
  subprocess), `WEB_SERVER_LOG_LEVEL` (uvicorn), `GST_DEBUG` (GStreamer
  native, integer `0-9`).

## Tests

ViPPET has two test suites:

| Suite      | Framework             | Location                   | Where it runs                  |
|------------|-----------------------|----------------------------|--------------------------------|
| Unit       | `unittest` + coverage | `vippet/tests/unit/`       | Inside the `test` Docker image |
| Functional | `pytest`              | `vippet/tests/functional/` | Local Python venv (`.venv`)    |

### How to run the tests

All test targets are available through the `Makefile`. Run them from the
repository root.

| Command           | What it does                                                        |
|-------------------|---------------------------------------------------------------------|
| `make test`       | Run the full unit-test suite with coverage (Docker, `cpu` profile). |
| `make test-smoke` | Run functional tests marked `smoke` (fast subset, local venv).      |
| `make test-full`  | Run the complete functional suite (local venv).                     |

#### Unit tests

```bash
make test
```

This builds an image with `TARGET=test`, mounts the source tree, and runs
`unittest discover` against `tests/unit/` (test files match the
`*_test.py` pattern). It then prints a coverage report to the terminal and
writes an HTML report to `/tmp/.vippet-coverage-html` inside the container.

Unit tests are device-agnostic and always run under the `cpu` profile, so
they need no GPU/NPU hardware.

#### Functional tests

Functional tests exercise the running service through `pytest` and execute
in a local virtual environment, which the target creates automatically on
first run (`.venv`, from `vippet/requirements-dev.txt`):

```bash
make test-smoke   # only tests marked `smoke` (quick check)
make test-full    # the full functional suite
```

Prerequisites:

- The VIPPET stack must be **running and reachable** before you start the
  tests (for example `make run`). The suite targets
  `http://localhost/api/v1` by default; override it with the
  `VIPPET_BASE_URL` environment variable.
- The models the tests rely on must already be **installed** through the
  Models page in the UI (or the `/api/v1/models` endpoints):
  - `make test-smoke` needs the default models (those marked
    `default: true` in `shared/models/supported_models.yaml`).
  - `make test-full` needs **all** models listed in
    `shared/models/supported_models.yaml`.

Tests that depend on optional hardware adapt automatically: pipeline
variants are selected from the devices reported by `/devices`, and USB
camera tests are skipped when `/cameras` reports no camera.

Under the hood these run, respectively:

```bash
python -m pytest --log-cli-level=INFO -m smoke vippet/tests/functional/
python -m pytest --log-cli-level=INFO          vippet/tests/functional/
```

### When you add a feature

- Put unit tests next to existing ones in `vippet/tests/unit/`; API route
  tests go under `vippet/tests/unit/api_tests/`. Name files `*_test.py` so
  `unittest discover` picks them up.
- Cover both the happy path and the error paths (invalid input, missing
  resource, conflicting state).
- For new API endpoints, add tests that exercise the route through FastAPI's
  `TestClient`, and add a functional test under
  `vippet/tests/functional/` (named `test_*.py`) when the behavior spans
  the running service.

## Linting and formatting

```bash
make lint        # markdownlint + ruff check + ruff format --check + pyright
make fix-linter  # ruff check --fix
make format      # ruff format
```

Rules:

- `ruff` runs with the project configuration.
- `pyright` runs in strict mode (see `pyrightconfig.json`). Avoid
  `# type: ignore`, when truly required add a one-line justification.
- Markdown files are linted by `markdownlint`.

## API schema and clients

The OpenAPI schema is the contract between the backend and the UI. Whenever
you add, remove, or change a route, a request body, or a response model you
must regenerate both the schema and the TypeScript client used by the UI.

### 1. Regenerate the OpenAPI schema

From the repository root:

```bash
make generate_openapi
```

This runs `generate_openapi.py` against the FastAPI app and writes the
resulting schema to `docs/user-guide/_assets/vippet.json`. Commit this file
together with your backend changes.

### 2. Regenerate the UI client

The UI consumes the schema through `@rtk-query/codegen-openapi`, configured
in `ui/src/api/api.config.json`. After the schema has been regenerated,
rebuild the typed client from the `ui/` directory:

```bash
cd ui
npm run generate:api
```

This produces `ui/src/api/api.generated.ts` (RTK Query hooks and types).
Commit the regenerated file together with the schema. If the build or the
UI starts reporting unknown endpoints or type mismatches after a backend
change, the most common cause is that one of these two steps was skipped.

## Adding a new route, quick checklist

1. Add or extend a Pydantic model in `vippet/api/api_schemas.py`.
2. Create the handler in `vippet/api/routes/<resource>.py` (or a new
   module, registered in `vippet/api/main.py`).
3. Use `async def`, type hints, and a markdown docstring with response
   codes and examples.
4. Delegate business logic to the appropriate manager, keep route
   handlers thin.
5. Add unit tests under `vippet/tests/unit/api_tests/`.
6. Run `make lint test`, then `make generate_openapi`, then
   `cd ui && npm run generate:api`.

## Important constraints

- **Do not commit `.env` files or model artifacts.**
- All new Dockerfiles must follow the existing multi-stage `prod` / `test`
  pattern.
- New environment variables must be documented in the README and in
  `AGENTS.md` (the *Key Environment Variables* table).

## Related pages

- [How to add a new pipeline](./new-pipeline.md)
- [How to add a new element](./new-element.md)
- [ViPPET Backend architecture](../architecture/vippet-be.md)
