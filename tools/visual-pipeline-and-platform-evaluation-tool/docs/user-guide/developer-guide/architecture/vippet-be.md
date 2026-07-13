# ViPPET Backend

The ViPPET backend (the `vippet-app` service) is a Python application that exposes the REST API used by the
UI, manages pipelines and models, and runs GStreamer / DL Streamer workloads on the underlying hardware. It is
designed to keep request handling fast and non-blocking, while the actual media processing happens in isolated
subprocesses.

## Core Stack

### Python 3.12 + FastAPI

The service is built on FastAPI running under uvicorn. Route handlers are `async`, request and response bodies
are described with Pydantic v2 models, and the OpenAPI schema is generated automatically. Swagger UI is
available at `/docs` and ReDoc at `/redoc` (both proxied through the UI nginx, and reachable directly on port
7860).

### Pydantic v2 Schemas

All API payloads are defined as Pydantic v2 models in `vippet/api/api_schemas.py`. The same schemas are reused
for validation, OpenAPI generation, and as the source of the typed RTK Query client consumed by the UI. See
[Backend contributing guide](../contributing/backend.md) for the regeneration workflow.

### OpenVINO, DL Streamer, GStreamer

Inference workloads are executed by GStreamer pipelines that use DL Streamer elements (`gva*`) backed by
OpenVINO™. Available hardware (CPU / GPU / NPU) is probed at startup through the OpenVINO™ Core in
`vippet/device.py`, and exposed through the `/devices` endpoint so the UI can offer the right per-device
pipeline variants.

### Subprocess Pipeline Runner

The backend does not embed a GStreamer main loop in the API process. Instead, every pipeline run is launched
as a separate subprocess through `pipeline_runner.py`, which spawns `gst_runner.py`. This keeps the API
responsive, isolates native crashes, and allows multiple pipelines to run concurrently with independent logs
and lifecycles.

### Docker Compose with Hardware Profiles

The backend ships as a container and is composed with sibling services (`vippet-ui`, `mediamtx`,
`model-download`, `metrics-manager`) via Docker Compose. Hardware capabilities are selected through
`COMPOSE_PROFILES` (`cpu`, `gpu`, `npu`), which is auto-detected by `setup_env.sh`.

### Developer Tooling

The backend uses `ruff` for linting and formatting, `pyright` for type checking, and `pytest` (with unit and
functional suites) for tests. All targets are wired into the top-level `Makefile` (`make lint`, `make format`,
`make test`, `make test-smoke`, `make test-full`).

## Runtime Architecture

### Layered Layout

The Python package under `vippet/` is organized in clear layers:

- `vippet/api/` - FastAPI app, routers, request / response schemas, and middleware.
- `vippet/managers/` - business logic and in-memory state (singletons, thread-safe where needed).
- `vippet/pipelines/` - built-in pipeline definitions (YAML) and the loader that turns them into runtime objects.
- `vippet/graph.py`, `vippet/pipeline_runner.py`, `vippet/gst_runner.py` - pipeline graph model,
  subprocess orchestration, and the low-level GStreamer runner that is executed as a child process.
- `vippet/device.py`, `vippet/video_encoder.py`, `vippet/video_decoder.py`, `vippet/camera.py`,
  `vippet/images.py`, `vippet/videos.py` - hardware and media helpers used by managers and runners.

### Application Startup

On startup the FastAPI `lifespan` hook (`vippet/api/main.py`) registers only the `health` router and
immediately starts a background initialization thread. That thread sequentially brings up `VideosManager`,
`ImagesManager`, `PipelineManager`, `PipelineTemplateManager`, and `ModelManager`, then registers the
remaining routers. The `AppStateManager` exposes the current phase (`STARTING`, `INITIALIZING`, `READY`,
`SHUTDOWN`) through the health endpoint, and the `InitializationMiddleware` rejects business calls until the
app is `READY`. This pattern lets Docker health checks succeed early without serving partially initialized
state.

### Request Lifecycle

A typical request flows through these stages:

1. The UI calls `/api/v1/...` (nginx proxies API calls to the backend on port 7860).
2. FastAPI validates the body and path / query parameters against Pydantic models.
3. The route handler delegates to a manager. Managers hold state and own all business rules.
4. For long-running or media-bound work (optimization, validation, density / performance tests), the manager
submits a job and returns a `job_id`. The actual execution happens in a worker thread that drives one or more
subprocess-based runs of `gst_runner.py`.
5. The UI polls the corresponding `/jobs/...` endpoint or subscribes to the SSE metrics stream for progress.

### Pipelines and Variants

A pipeline is a logical workload (for example "License plate recognition") with one or more device-specific
variants (`CPU`, `GPU`, `NPU`, `GPU_NPU`). Built-in pipelines are YAML files under `vippet/pipelines/`,
auto-discovered by `PipelineLoader.list()` and registered as `read_only` (source `PREDEFINED`). User-defined
pipelines are created at runtime through `POST /pipelines` (source `USER_CREATED`). The same `PipelineManager`
owns both kinds. See the [New pipeline guide](../contributing/new-pipeline.md) for the YAML schema and REST
payload.

### Pipeline Graph Model

Each variant carries a full GStreamer description and a graph representation (`pipeline_graph`) plus a
simplified view (`pipeline_graph_simple`) used by the visual editor. `vippet/graph.py` converts between the
GStreamer description and the graph form, and applies the `SIMPLE_VIEW_VISIBLE_ELEMENTS` /
`SIMPLE_VIEW_INVISIBLE_ELEMENTS` filtering rules that decide which elements appear in the simplified canvas.

### Automatic Graph Transformations

`PipelineManager.build_pipeline_command()` does not run the variant graph as-is. For every stream it
applies a small set of deterministic transformations defined in `vippet/graph.py`, so the same graph can
be reused across different output modes without changes to the YAML or the saved user definition:

- **Intermediate sink rewriting** (`prepare_intermediate_output_sinks`) — gives every non-fakesink
  terminal a unique, stream-scoped file location under the job output directory.
- **Main output placeholder** (`prepare_main_output_placeholder`) — when `output_mode` is `file` or
  `live_stream`, the default `fakesink name=default_output_sink` is converted to an
  `OUTPUT_PLACEHOLDER` node. It is replaced later by the encoder + filesink (for `file`) or by the
  encoder + rtspclientsink (for `live_stream`) subpipeline built by `video_encoder`.
- **Metadata file injection** (`inject_metadata_file_paths`) — when `metadata_mode=file`, every
  `gvametapublish` node gets a unique file path under the job metadata directory.
- **Automatic `gvawatermark` stripping** (`strip_watermark_if_all_sinks_are_fake`) — removes every
  `gvawatermark` node when the only terminals left are fakesinks, i.e., there is no rendered video
  output that would consume the overlay. The watermark is preserved whenever an `OUTPUT_PLACEHOLDER`
  is present (`output_mode=file` or `live_stream`) or any non-fakesink terminal exists in the graph
  (for example a `splitmuxsink` in NVR-style pipelines that records the stream itself). This keeps
  the default `output_mode=disabled` measurement free of the overlay-rendering cost without
  affecting live view, file output, or pipelines that persist the video.
- **Unique element names and source/sink identifiers** (`unify_all_element_names`,
  `apply_stream_identifiers`) — assigns deterministic, stream-unique names to every element so the
  latency tracer can correlate its rows back to a specific source/sink pair.

### Job and Metrics Flow

Tests, optimization runs, and validation runs are tracked as jobs. Each job has a status (`PENDING`,
`RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`), a structured summary, and per-stream metadata. Live runtime
metrics (CPU, GPU, NPU usage, power, memory, FPS) are collected by the sibling `metrics-manager` service from
Telegraf and qmassa, and streamed to the UI as Server-Sent Events through the nginx proxy at
`/metrics/stream`. Per-frame inference metadata produced by DL Streamer is captured by `MetadataManager`, which
tails the metadata files and streams records to the UI through SSE.

## Managers

The `managers/` package holds the business-logic layer. Each manager is responsible for one domain and is the
only component allowed to mutate state for that domain. Most managers are thread-safe singletons.

### AppStateManager

Tracks the lifecycle state of the application (`STARTING`, `INITIALIZING`, `READY`, `SHUTDOWN`) and an
optional human-readable message. Used by the health endpoint and by `InitializationMiddleware` to gate
traffic. Key methods: `set_status()`, `status()`, `is_ready()`, `is_healthy()`.

### PipelineManager

The central registry of pipelines and variants. Loads predefined pipelines from YAML on startup, accepts
user-created pipelines through the API, and builds the runtime command lines used by the pipeline runner. Key
methods: `add_pipeline()`, `get_pipelines()`, `get_pipeline_by_id()`, `update_pipeline()`,
`delete_pipeline_by_id()`, `add_variant()`, `update_variant()`, `delete_variant()`,
`load_predefined_pipelines()`, `build_pipeline_command()`, and the `validate_and_convert_advanced_to_simple()`
/ `validate_and_convert_simple_to_advanced()` graph converters.

### PipelineTemplateManager

Read-only registry of reusable pipeline templates that the UI offers as starting points when creating a new
user-defined pipeline. Key methods: `get_templates()`, `get_template_by_id()`.

### ModelManager

Owns the catalog of supported models (`supported_models.yaml`) and the registry of installed models on disk.
Triggers downloads through the `model-download` microservice, tracks download jobs, supports user uploads of
custom models, and computes the `used_by_pipelines` field shown in the UI. Key methods: `list_models()`,
`start_download()`, `upload_model()`, `get_job()`, `get_all_jobs()`,
`find_installed_uploaded_model_by_display_name()`.

### CameraManager

Discovers media input sources: local USB cameras under `/dev/video*` and network (RTSP / ONVIF) cameras
through the `onvif_discovery` agent. Resolves user-supplied identifiers to concrete device descriptors and
exposes capabilities and encodings to the rest of the stack. Key methods: `discover_usb_cameras()`,
`discover_network_cameras()`, `discover_all_cameras()`, `get_camera_by_id()`, `get_encoding_for_rtsp_url()`.

### TestsManager

Runs performance and density benchmarks. Performance tests run a single pipeline variant under defined
conditions; density tests use the algorithm in `benchmark.py` to find the maximum number of concurrent streams
the hardware can sustain. Density supports two modes selected automatically from the request shape:
**classic mode** (search variable = total stream count, distributed across pipelines by `stream_rate`) and
**mixed mode** (exactly two pipelines; one pinned to a fixed `streams` value, the other incremented by the
search variable). Each invocation returns a `job_id` that the UI can poll, summarize, or cancel. Key
methods: `test_performance()`, `test_density()`, `get_job_status()`, `get_job_summary()`,
`get_job_statuses_by_type()`, `stop_job()`.

### OptimizationManager

Coordinates model optimization runs (preprocessing + optimization), driven by the `OptimizationRunner` helper.
Designed for long-running, cancellable jobs and exposes status / summary endpoints used by the UI to render
progress. Key methods: `run_optimization()`, `get_job_status()`, `get_all_job_statuses()`,
`get_job_summary()`.

### ValidationManager

Runs accuracy and correctness checks against pipeline variants (for example comparing inference output against
a reference) and tracks each run as a job. Key methods: `run_validation()`, `get_job_status()`,
`get_all_job_statuses()`, `get_job_summary()`.

### MetadataManager

Tails the per-job DL Streamer metadata files written during pipeline runs and exposes them to the UI both as
paged snapshots and as live Server-Sent Events streams. Key methods: `register_job()`, `get_snapshot()`,
`resolve_file_index()`, `stream_events()`, `stop_tailing()`.

## Sibling Services and Integrations

The backend does not run alone. It cooperates with a small set of sibling containers managed by Docker Compose:

- **`vippet-ui`** - serves the React app and proxies `/api/v1/*`, `/metrics/*`, and `/docs` to the backend on port 7860.
- **`mediamtx`** - RTSP server used for live preview streams. The backend publishes live encoded output
  to `rtsp://mediamtx:8554/<stream-name>` (configurable through `LIVE_STREAM_SERVER_HOST` /
  `LIVE_STREAM_SERVER_PORT`).
- **`model-download`** - dedicated microservice that performs the actual model downloads.
  `ModelManager` calls into it and polls job status; the backend exposes a stable `/models` API on top.
- **`metrics-manager`** - collects hardware telemetry via Telegraf and qmassa and pushes it to clients
  over SSE. The UI subscribes to `/metrics/stream`, which nginx routes to this service.
- **`onvif_discovery`** (built locally) - a short-lived helper used by `CameraManager` to discover
  ONVIF-capable network cameras on the local network.

## Summary

The ViPPET backend keeps a clear separation between a thin async FastAPI surface and a manager-centric
business-logic layer, while pushing all heavy media work into isolated GStreamer subprocesses. Pipelines,
models, cameras, jobs, and metrics each have a dedicated manager with a well-defined API, and the OpenAPI
schema (browsable at `/docs`) is the contract that ties everything to the typed UI client. For day-to-day work
on the backend, start with the [Backend contributing guide](../contributing/backend.md); to add a new
workload, see [Adding a new pipeline](../contributing/new-pipeline.md).
