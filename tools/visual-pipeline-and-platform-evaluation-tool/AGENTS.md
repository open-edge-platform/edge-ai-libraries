# Visual Pipeline and Platform Evaluation Tool (ViPPET)

## Project Overview

ViPPET is a tool for evaluating Intel® hardware options for AI workloads. It enables benchmarking
of AI inference pipelines (GStreamer + OpenVINO™ + DLStreamer), collecting hardware metrics
(CPU/GPU/NPU usage, power, memory), and visualizing results in a React-based UI.

## Repository Structure

```text
tools/visual-pipeline-and-platform-evaluation-tool/
├── vippet/               # Backend: Python/FastAPI application
│   ├── api/              # REST + WebSocket API (FastAPI, port 7860)
│   │   ├── main.py       # App entrypoint, router registration
│   │   ├── api_schemas.py # Pydantic request/response models
│   │   └── routes/       # API route handlers (pipelines, models, jobs, etc.)
│   ├── managers/         # Business logic managers (pipeline, camera, job)
│   ├── pipelines/        # Built-in GStreamer pipeline definitions (YAML)
│   ├── benchmark.py      # Density benchmarking logic
│   ├── pipeline_runner.py # Subprocess-based GStreamer pipeline executor
│   ├── gst_runner.py     # Low-level GStreamer runner (called as subprocess)
│   ├── graph.py          # GStreamer pipeline graph representation
│   ├── device.py         # OpenVINO device detection (CPU/GPU/NPU)
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
├── collector/            # Hardware metrics collector (Telegraf + qmassa)
│   ├── qmassa_reader.py  # Reads GPU metrics from qmassa FIFO and emits InfluxDB line protocol
│   └── supervisord.conf  # Runs qmassa + telegraf as supervised processes
├── video_generator/      # Synthetic test video generator (Python + GStreamer)
├── models/               # Model download and management scripts
│   └── model_manager.sh  # Interactive/automated model installer
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

# 3. Install AI models (interactive)
make install-models-once

# 4. Build and run all services
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

| Target          | Description                           |
|-----------------|---------------------------------------|
| `make build`    | Build all Docker images               |
| `make run`      | Start all services via Docker Compose |
| `make stop`     | Stop all services                     |
| `make clean`    | Stop and remove containers/volumes    |
| `make shell`    | Open shell in vippet container        |
| `make shell-ui` | Open shell in UI container            |
| `make test`     | Run tests in Docker                   |

## API

- **Backend API**: `http://localhost:7860/api/v1/` (FastAPI, auto-documented at `/docs`)
- **UI**: `http://localhost:80`
- **RTSP live streams**: `rtsp://localhost:8554/{stream_name}` (via mediamtx)
- **WebSocket metrics**: `ws://localhost:7860/metrics/ws`

The OpenAPI schema can be regenerated with:

```bash
make generate_openapi
```

## Docker Compose Services

| Service     | Description                               | Port |
|-------------|-------------------------------------------|------|
| `vippet`    | Backend (FastAPI)                         | 7860 |
| `vippet-ui` | Frontend (Nginx)                          | 80   |
| `mediamtx`  | RTSP server                               | 8554 |
| `models`    | Model installer (profile: `do-not-start`) | -    |
| `collector` | Metrics collector (profile: `gpu`/`npu`)  | -    |

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

| Variable                         | Description                                                  | Default                                                    |
|----------------------------------|--------------------------------------------------------------|------------------------------------------------------------|
| `APP_LOG_LEVEL`                  | Python logging level for the application                     | `INFO`                                                     |
| `RUNNER_LOG_LEVEL`               | Logging level for gst_runner.py subprocess                   | `INFO`                                                     |
| `WEB_SERVER_LOG_LEVEL`           | Logging level for uvicorn web server                         | `WARNING`                                                  |
| `METRICS_LOG_LEVEL`              | Logging level for metrics WebSocket routes                   | `INFO`                                                     |
| `GST_DEBUG`                      | GStreamer native debug level (integer, 0-9)                  | `1`                                                        |
| `MODELS_PATH`                    | Path to downloaded models                                    | `/models/output`                                           |
| `SUPPORTED_MODELS_FILE`          | Path to supported_models.yaml                                | `/models/supported_models.yaml`                            |
| `INPUT_VIDEO_DIR`                | Path to input videos                                         | `/videos/input`                                            |
| `OUTPUT_VIDEO_DIR`               | Path to output videos                                        | `/videos/output`                                           |
| `SIMPLE_VIEW_VISIBLE_ELEMENTS`   | Glob patterns for elements shown in simplified pipeline view | `*src,urisourcebin,gva*,*sink,source`                      |
| `SIMPLE_VIEW_INVISIBLE_ELEMENTS` | Element names hidden from simplified pipeline view           | `gvafpscounter,gvametapublish,gvametaconvert,gvawatermark` |
| `LIVE_STREAM_SERVER_HOST`        | RTSP server hostname                                         | `mediamtx`                                                 |
| `LIVE_STREAM_SERVER_PORT`        | RTSP server port                                             | `8554`                                                     |
| `RTSPSRC_DEFAULT_LATENCY_MS`     | Default latency in ms for rtspsrc elements                   | `100`                                                      |
| `COMPOSE_PROFILES`               | Hardware profile (cpu/gpu/npu)                               | Auto-detected                                              |
| `PYTHONPATH`                     | Python module search path                                    | `/app`                                                     |

## Important Notes for AI Agents

- **Never modify** `shared/` directory contents in code — it's a runtime-mounted volume
- The `vippet/` Python package uses relative imports — always run from the container context
- GStreamer pipelines are executed as **subprocesses** via `gst_runner.py`, not directly in Python
- Hardware device detection happens at startup via `device.py` (OpenVINO Core)
- The `models` service must be run separately before `vippet` to install required AI models
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

- **Models not found**: Run `make install-models-once` first
- **Permission denied on /dev/video***: Add user to `video` group
- **GPU not detected**: Check `setup_env.sh` output and Docker GPU support
- **Port conflicts**: Check if ports 80, 7860, 8554 are available
