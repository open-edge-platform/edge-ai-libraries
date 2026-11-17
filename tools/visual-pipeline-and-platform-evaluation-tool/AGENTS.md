# Visual Pipeline and Platform Evaluation Tool (ViPPET)

## Project Overview

ViPPET is a tool for evaluating Intel® hardware options for AI workloads. It enables benchmarking
of AI inference pipelines (GStreamer + OpenVINO™ + DLStreamer), collecting hardware metrics
(CPU/GPU/NPU usage, power, memory), and visualizing results in a React-based UI.

## Repository Structure

```text
tools/visual-pipeline-and-platform-evaluation-tool/
├── vippet/               # Backend: Python/FastAPI application
│   ├── api/              # REST API (FastAPI, port 7860)
│   │   ├── main.py       # App entrypoint, router registration
│   │   ├── api_schemas.py # Pydantic request/response models
│   │   └── routes/       # API route handlers (pipelines, models, jobs, etc.)
│   ├── managers/         # Business logic managers (pipeline, camera, job)
│   ├── pipelines/        # Built-in GStreamer pipeline definitions (YAML)
│   ├── models/           # Model catalog (one YAML file per model, baked into image)
│   ├── benchmarks/       # Built-in benchmark suite definitions (YAML)
│   ├── db_seed.py        # Startup DB seeding from pipelines/, benchmarks/, models/
│   ├── database.py       # Async SQLAlchemy engine/session setup
│   ├── orm_models.py     # SQLAlchemy ORM models
│   ├── benchmark.py      # Density benchmarking logic
│   ├── dlsps2_runner.py  # Runs pipelines on DL Streamer Pipeline Server 2.0 (REST)
│   ├── pipeline_events.py # Live pipeline events read from JSON Lines files
│   ├── pipeline_runner.py # Pipeline run result types
│   ├── graph.py          # GStreamer pipeline graph representation
│   ├── device.py         # Device list (CPU/GPU/NPU) from DLSPS 2.0
│   ├── video_encoder.py  # Video encoding/live-streaming management
│   ├── requirements.txt  # Production Python dependencies
│   └── Dockerfile        # Multi-stage Docker image (prod/test)
├── ui/                   # Frontend: React + TypeScript + Vite application
│   ├── src/
│   │   ├── main.tsx      # App entrypoint
│   │   ├── routes.ts     # React Router configuration
│   │   ├── features/     # Feature-based modules (metrics, pipelines, etc.)
│   │   ├── components/   # Shared UI components
│   │   ├── store/        # Redux store + redux-persist
│   │   └── config/       # Navigation and app config
│   ├── vite.config.ts    # Vite config with API proxy rules
│   └── Dockerfile        # Nginx-based production image
├── video_generator/      # Synthetic test video generator (Python + GStreamer)
├── shared/               # Runtime-mounted volumes (videos, models, scripts)
├── compose.yml           # Main Docker Compose file
├── compose.dev.yml       # Dev override (disables healthcheck, mounts source)
├── compose.cpu.yml       # CPU-only profile override
├── Makefile              # Main build/test/run targets
└── setup_env.sh          # Auto-detects hardware (NPU/GPU/CPU) and writes .env
```

## Tech Stack

| Layer            | Technology                                                                |
|------------------|---------------------------------------------------------------------------|
| Backend          | Python 3.12, FastAPI, uvicorn, Pydantic v2                                |
| AI Inference     | OpenVINO™ 2025.x, DLStreamer 2026.x, GStreamer 1.0                        |
| Frontend         | React 19, shadcn components, react-hook-form, zod, recharts, react-router |
| Containerization | Docker Compose with hardware profiles: `cpu`, `gpu`, `npu`                |
| Metrics          | Telegraf, qmassa (GPU), InfluxDB line protocol                            |
| Type Checking    | Pyright (Python), TypeScript strict mode                                  |
| Linting          | ruff (Python), ESLint (TypeScript)                                        |

## Build, Run & Test

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for local development)
- Node.js 18+ (for UI development)

### Setup and Run

```bash
# 1. Auto-detect hardware and generate .env
./setup_env.sh

# 2. Set up shared directories
make env-setup

# 3. Build and run all services
make build
make run
```

### Development (with live code reload)

```bash
make build-dev
make run-dev
```

### Tests

```bash
make test
```

### Linting

```bash
make lint        # Run all linters (mdlint, ruff, pyright)
make fix-linter  # Auto-fix ruff issues
make format      # Auto-format with ruff
```

### Individual Make Targets

| Target              | Description                                                          |
| ------------------- | -------------------------------------------------------------------- |
| `make build`        | Build all Docker images (DLSPS 2.0 skipped if `DLSPS2_IMAGE` is set) |
| `make run`          | Start all services via Docker Compose                                |
| `make run-prebuilt` | Pull and start the published images (`latest` on main); never builds |
| `make stop`         | Stop all services                                                    |
| `make clean`        | Stop and remove containers/volumes                                   |
| `make shell`        | Open shell in vippet container                                       |
| `make shell-ui`     | Open shell in UI container                                           |
| `make shell-dlsps`  | Open shell in DL Streamer Pipeline Server 2.0 container              |
| `make test`         | Run tests in Docker                                                  |

## API

- **Backend API**: `http://localhost:7860/api/v1/` (FastAPI, auto-documented at `/docs`)
- **UI**: `http://localhost:80`
- **RTSP live streams**: `rtsp://localhost:8554/{stream_name}` (via mediamtx)
- **SSE metrics stream**: `http://localhost/metrics/stream` (proxied by nginx to metrics-manager)

The OpenAPI schema can be regenerated with:

```bash
make generate_openapi
```

## Docker Compose Services

| Service                      | Description                                                                  | Port                             |
|------------------------------|------------------------------------------------------------------------------|----------------------------------|
| `vippet`                     | Backend (FastAPI)                                                            | 7860                             |
| `vippet-ui`                  | Frontend (Nginx)                                                             | 80                               |
| `mediamtx`                   | RTSP server                                                                  | 8554                             |
| `model-download`             | Model download microservice                                                  | 8000                             |
| `metrics-manager`            | Metrics collector                                                            | 9090                             |
| `dlstreamer-pipeline-server` | DL Streamer Pipeline Server 2.0; runs every pipeline                         | 8080, compose network only       |
| `vippet-plugins`             | One-shot; copies `vippet/gst_plugins` to the `vippet-gst-plugins` volume     | -                                |

Hardware profiles (`COMPOSE_PROFILES`): `cpu`, `gpu`, `npu` — set automatically by `setup_env.sh`.

## Coding Standards

### Python (backend)

- Python 3.12, type hints everywhere
- Pydantic v2 for all API schemas (use `model_dump()`, not `.dict()`)
- `async`/`await` for all FastAPI route handlers
- Use `logging` module (never `print()`)
- Follow ruff and pyright rules — no type: ignore without justification
- Tests use pytest; place in `vippet/tests/`

### TypeScript (frontend)

- Strict TypeScript — no `any` types
- Feature-based folder structure under `src/features/`
- Redux Toolkit for global state; React Query for server state
- Tailwind CSS for all styling
- Follow existing ESLint configuration

### General

- License header required: `SPDX-License-Identifier: Apache-2.0`
- All new Dockerfiles must follow the existing multi-stage pattern
- Do not commit `.env` files or model files

## Key Environment Variables (vippet service)

| Variable                           | Description                                                  | Default                                                    |
| ---------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------- |
| `APP_LOG_LEVEL`                    | Python logging level for the application                     | `INFO`                                                     |
| `WEB_SERVER_LOG_LEVEL`             | Logging level for uvicorn web server                         | `WARNING`                                                  |
| `GST_DEBUG`                        | GStreamer native debug level (integer, 0-9)                  | `1`                                                        |
| `MODELS_PATH`                      | Path to downloaded models                                    | `/models/output`                                           |
| `AUTO_VIDEO_DIR`                   | Path to auto-downloaded videos                               | `/videos/input/auto`                                       |
| `UPLOADED_VIDEO_DIR`               | Path to user-uploaded videos                                 | `/videos/input/uploaded`                                   |
| `DEFAULT_RECORDINGS_FILE`          | Path to the YAML listing recordings to auto-download         | `/videos/default_recordings.yaml`                          |
| `UPLOAD_ALLOWED_EXTENSIONS`        | Comma-separated allow-list of upload file extensions         | `mp4,mkv,mov,avi,ts,264,avc,h265,hevc`                     |
| `UPLOAD_ALLOWED_CONTAINERS`        | Comma-separated allow-list of upload container formats       | `mp4,mov,mkv,avi,mpegts,raw`                               |
| `UPLOAD_ALLOWED_CODECS`            | Comma-separated allow-list of upload video codecs            | `h264,h265`                                                |
| `UPLOAD_MAX_SIZE_BYTES`            | Maximum accepted upload body size in bytes                   | `2147483648` (2 GiB)                                       |
| `OUTPUT_VIDEO_DIR`                 | Path to output videos                                        | `/videos/output`                                           |
| `UPLOADED_IMAGES_DIR`              | Path to user-uploaded image sets                             | `/images/input/uploaded`                                   |
| `SIMPLE_VIEW_VISIBLE_ELEMENTS`     | Glob patterns for elements shown in simplified pipeline view | `*src,urisourcebin,gva*,*sink,source,videoscale`           |
| `SIMPLE_VIEW_INVISIBLE_ELEMENTS`   | Element names hidden from simplified pipeline view           | `gvafpscounter,gvametapublish,gvametaconvert,gvawatermark` |
| `LIVE_STREAM_SERVER_HOST`          | RTSP server hostname                                         | `mediamtx`                                                 |
| `LIVE_STREAM_SERVER_PORT`          | RTSP server port                                             | `8554`                                                     |
| `RTSPSRC_DEFAULT_LATENCY_MS`       | Default latency in ms for rtspsrc elements                   | `100`                                                      |
| `BENCHMARK_ENABLE_LATENCY_METRICS` | Enable DLStreamer latency tracer for benchmark test cases    | `true`                                                     |
| `DLSPS2_BASE_URL`                  | DL Streamer Pipeline Server 2.0 REST base URL                | `http://dlstreamer-pipeline-server:8080`                   |
| `DLSPS2_VERIFY_TLS`                | Verify the server's TLS certificate (https base URL)         | `false`                                                    |
| `DLSPS2_OTEL`                      | Server exports its metrics to metrics-manager (OTLP)         | `true`                                                     |
| `DLSPS2_OTEL_INTERVAL_MS`          | Server metrics export interval in milliseconds               | `1000`                                                     |
| `DLSPS2_GST_TRACERS`               | Server `GST_TRACERS`; `latency_tracer` for latency metrics   | `latency_tracer(...,post-metrics=true)`; empty disables    |
| `COMPOSE_PROFILES`                 | Hardware profile (cpu/gpu/npu)                               | Auto-detected                                              |
| `PYTHONPATH`                       | Python module search path                                    | `/app`                                                     |

Build and compose variables for the pipeline server: `DLSPS2_IMAGE` (use a published
`intel/dlstreamer-pipeline-server:<tag>-2.0` image instead of building it), `DLSPS2_BASE_IMAGE` (base image of the
source build, defaults to `DLSTREAMER_IMAGE`) and `DLSPS2_REST_SERVER_PORT` (port its REST API binds on the host with
`GIGE=1`, default `8081`). `make run-prebuilt` uses `DLSPS2_IMAGE`, or `PREBUILT_DLSPS2_IMAGE` from the `Makefile`.
The REST API is not published on the host otherwise.

## Important Notes for AI Agents

- **Never modify** `shared/` directory contents in code — it's a runtime-mounted volume
- The `vippet/` Python package uses relative imports — always run from the container context
- GStreamer pipelines run on **DL Streamer Pipeline Server 2.0** (`dlstreamer-pipeline-server`), sent over REST
  by `dlsps2_runner.py`, one server instance per stream; they are not executed in the vippet process. The DL
  Streamer pipeline optimizer still runs in vippet
- Hardware devices come from the DLSPS 2.0 `GET /devices` endpoint, read by
  `device.py` on first use and cached
- AI models are installed at runtime via the `model-download` microservice;
  vippet-app exposes `/api/v1/models` endpoints (and the UI Models page) to trigger installs
- The model catalog lives in `vippet/models/` (one YAML file per model), baked into the
  image at build time and synced insert-only into the DB at startup via `db_seed.py`;
  adding/editing a model requires an image rebuild (`make build`), not just a restart
- Video input sources: files from `shared/videos/input/`, USB cameras (`/dev/video*`), RTSP/ONVIF cameras

## Documentation Standards

### Docstrings for API endpoints (Flask/FastAPI)

Use markdown in docstrings
Swagger/OpenAPI automatically renders markdown as beautiful documentation

Example:

```python
@app.route('/pipelines', methods=['POST'])
def create_pipeline(body: schemas.PipelineDefinition) -> JSONResponse:
    """
    # Create Pipeline

    Create a new user-defined pipeline with automatic metadata generation.

    ## Operation
    1. Enforce `USER_CREATED` source
    2. Delegate to `PipelineManager.add_pipeline()`
    3. Return generated pipeline ID

    ## Auto-Generated Fields
    The backend automatically sets:
    - Pipeline ID (generated from name)
    - Timestamps (`created_at` and `modified_at`)
    - Variant IDs (generated from variant names)
    - Variant `read_only=False` for all variants
    - Pipeline `thumbnail=None` (user-created pipelines)

    ## Request Body
    **`PipelineDefinition`** with:
    - `name` *(required)* - Non-empty pipeline name
    - `description` *(required)* - Human-readable description
    - `source` *(ignored)* - Forced to `USER_CREATED`
    - `tags` *(optional)* - List of categorization tags
    - `variants` *(required)* - List of `VariantCreate` objects

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 201 | `PipelineCreationResponse` with generated pipeline `id` |
    | 400 | `MessageResponse` - Invalid pipeline definition |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - Valid PipelineDefinition
    - PipelineManager successfully creates pipeline

    ### ❌ Failure
    - Invalid pipeline definition → 400
    - Unhandled error → 500

    ## Examples

    ### Request
    ```json
    {
      "name": "vehicle-detection",
      "description": "Simple vehicle detection pipeline",
      "tags": ["detection", "vehicle"],
      "variants": [
        {
          "name": "CPU",
          "pipeline_graph": {...},
          "pipeline_graph_simple": {...}
        }
      ]
    }
    ```

    ### Success Response (201)
    ```json
    {
      "id": "pipeline-a3f5d9e1"
    }
    ```

    ### Error Response (400)
    ```json
    {
      "message": "Pipeline name cannot be empty"
    }
    ```
    """
```

### Docstrings for regular functions (utilities, helpers, classes)

Use standard docstring format (Google/NumPy/Sphinx style)
No markdown - better readability in IDE hover/tooltips

Example:

```python
def calculate_total(items, tax_rate=0.23):
    """
    Calculate total price including tax for given items.

    Args:
        items (list): List of dictionaries containing item data with 'price' key
        tax_rate (float, optional): Tax rate as decimal. Defaults to 0.23.

    Returns:
        float: Total price including tax, rounded to 2 decimal places

    Raises:
        ValueError: If tax_rate is negative or items list is empty
        KeyError: If any item missing 'price' key

    Example:
        >>> items = [{'price': 10.0}, {'price': 20.0}]
        >>> calculate_total(items, 0.20)
        36.0
    """
```

### API Documentation

- All FastAPI endpoints automatically generate OpenAPI docs at `/docs`
- Use Pydantic models with Field descriptions for request/response schemas
- Add endpoint descriptions and examples in route decorators

## Naming Conventions

### Python

- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

### TypeScript

- Functions/variables: `camelCase`
- Components: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Types/Interfaces: `PascalCase`

## Python Typing Rules (Python 3.12+)

## Scope

Use **Python 3.12+ only**.
Do not write backward-compatible typing.

---

## Rules

- Use built-in generics: `list`, `dict`, `set`, `tuple`
- Use `|`
- Use `T | None`
- Do not use `List`, `Dict`, `Union`, `Optional`
- Import from `typing` only when necessary

---

## Correct Examples

```python
def process(data: list[dict[str, int]] | None) -> bool:
    return data is not None
```

```python
from typing import Literal

def open_file(mode: Literal["r", "w"]) -> None:
    ...
```

---

## Do Not Use

```python
List[int]
Dict[str, int]
Union[int, str]
Optional[str]
```

### README Updates

- Update relevant README files when adding new features or changing APIs
- Keep installation and setup instructions current
- Document any new environment variables or configuration options

## Common Issues

- **Models not found**: Install required models through the UI (Models page) or the `/api/v1/models` endpoints;
  vippet-app proxies installs to the `model-download` service
- **New model not showing up**: `vippet/models/*.yaml` is baked into the image, not volume-mounted;
  rebuild (`make build`) and restart, or use `make run-dev` (bind-mounts `vippet/`) for a restart-only workflow
- **Permission denied on /dev/video***: Add user to `video` group
- **GPU not detected**: Check `setup_env.sh` output and Docker GPU support
- **Port conflicts**: Check if ports 80, 7860, 8554 are available
