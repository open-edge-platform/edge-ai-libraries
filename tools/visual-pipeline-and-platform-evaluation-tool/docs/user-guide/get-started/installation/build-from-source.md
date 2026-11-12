# Build from Source

Build the Visual Pipeline and Platform Evaluation Tool from source to customize, debug, or extend its
functionality. In this guide, the following tasks are covered:

- Setting up the development environment.
- Compiling the source code and resolving dependencies.
- Generating a runnable build for local testing or deployment.

This guide is intended for developers working directly with the source code.

## Prerequisites

Before starting, ensure the following:

- **System requirements**: The system meets the [minimum requirements](./system-requirements.md).
- **Internet access**: The host has outbound internet connectivity. Base images, apt and Python packages, npm
  dependencies, sample videos, and models are downloaded during the build and on first start. Offline or
  air-gapped installation is not supported. See
  [Network Requirements](./system-requirements.md#network-requirements).
- **Docker platform**: **Docker Engine** is installed. On Linux, install it from the Docker apt repository, see
  [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/), then complete the
  [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/) to run Docker as a non-root user.

  > [!NOTE]
   > Do not use Docker Desktop on Linux. It runs the Docker daemon inside a virtual machine that is not forwarding GPU
   > device on Linux (yet).

- **Dependencies installed**:
  - **Git**: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).
  - **Make**: Standard build tool, typically provided by the `build-essential` (or equivalent) package on Linux.

For GPU and/or NPU usage, appropriate drivers must be installed. The recommended method is to use the DLS installation
script, which detects available devices and installs the required drivers. Follow the `Prerequisites` section in
[Install Guide Ubuntu](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/install/install_guide_ubuntu.html#prerequisites).

> [!NOTE]
> The same steps apply to Ubuntu 24.04 running under WSL 2 on Windows - run all commands
> inside the WSL distribution. On WSL, only the CPU and GPU (WSL) variants are supported. See
> [System Requirements](./system-requirements.md#windows-subsystem-for-linux-wsl).

This guide assumes basic familiarity with Git commands and terminal usage. For more information, see
[Git Documentation](https://git-scm.com/doc).

Before building, review the [Pre-Installation Steps](./pre-installation-steps.md) for optional
configuration such as the Hugging Face access token used to download models from the
Hugging Face Hub.

## Steps to Build

1. Clone the repository:

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
   cd edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool
   ```

1. Build and start the application:

   ```bash
   make build run
   ```

   Both `make build` and `make run` automatically invoke `setup_env.sh`, which detects the
   available hardware (CPU/GPU/NPU) and writes the appropriate `.env` file. They also create
   the required directories under `shared/`.

   The images are tagged with the version of the checked-out sources (for example `2026.3.0-dev`), or with
   `DOCKER_TAG` if it is set in the environment. `make run` does not rebuild images: after changing the
   sources, run `make build` again. To run published images instead, see
   [Use Pre-Built Docker Images](./docker-compose.md).

1. Verify that the application is running:

   ```bash
   docker compose ps
   ```

1. Access the application:

   Open a browser and navigate to `http://localhost` (or `http://<HOST-IP>`) to access
   the Visual Pipeline and Platform Evaluation Tool UI.

1. Access the application API documentation:

   Open a browser and navigate to `http://localhost/api/v1/docs` (or `http://<HOST-IP>/api/v1/docs`)
   to access the Swagger UI.

## Pipeline execution on DL Streamer Pipeline Server 2.0

Every pipeline runs on a
[DL Streamer Pipeline Server 2.0](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/dlstreamer-pipeline-server/dlsps2/README.md)
container, the `dlstreamer-pipeline-server` service. The server runs:

- pipeline validation;
- performance and density tests and benchmarks, with every stream as its own server instance, so the job
  status also reports the slowest stream's FPS, and a density test counts a stream count as passing only if
  its slowest stream reaches the FPS floor;
- the conversion of videos to `.ts` for looping.

`make build` builds the server image from `microservices/dlstreamer-pipeline-server/dlsps2` in the same
repository, on the same DL Streamer base image as `vippet` unless `DLSPS2_BASE_IMAGE` is set. The server gets
the same devices as `vippet`. The
one-shot `vippet-plugins` service copies the custom elements in `vippet/gst_plugins/` from the `vippet` image
into the `vippet-gst-plugins` Docker volume, from where the server loads them. `vippet` reads the list of available GStreamer
elements from the server, so the decoders and encoders it picks are those of the server.

To use a published server image instead of building one, set `DLSPS2_IMAGE` to one of the
`-2.0` tags on [Docker Hub](https://hub.docker.com/r/intel/dlstreamer-pipeline-server/tags).
`make build` then skips the server, and `make run` pulls the image:

```bash
export DLSPS2_IMAGE=intel/dlstreamer-pipeline-server:2026.3.0-ubuntu24-2.0-rc1
make build run
```

`make run-prebuilt` also pulls the server image: `DLSPS2_IMAGE` if it is set, otherwise
`PREBUILT_DLSPS2_IMAGE` from the `Makefile`.

The server's REST API is not published on the host: `vippet` reaches it over the compose network. To query it,
run e.g. `docker exec vippet curl -s http://dlstreamer-pipeline-server:8080/pipelines/status`. Use
`docker logs -f dlstreamer-pipeline-server` to follow its log, or `make shell-dlsps` to open a shell in it.

### Latency and VLM metrics

The server exports its own per-instance metrics over OpenTelemetry to `metrics-manager` (`DLSPS2_OTEL`,
default `true`). `DLSPS2_OTEL_INTERVAL_MS` sets the export interval (default `1000`). `vippet` reads the
latency and VLM series of its own instances from `metrics-manager` and republishes them under the job. Each
republished sample aggregates one export period: the latency windows of that period, or the mean over its
`gvagenai` requests. After a run, `vippet` waits for the server's final export, for at most
`DLSPS2_OTEL_INTERVAL_MS` plus two seconds. The live FPS chart in the UI comes from `vippet`, not from
these exports.

VLM metrics need `metrics=true` on `gvagenai`. `vippet` adds `post-metrics=true` to such an element when the
server's `gvagenai` has that property, as reported by the server's `GET /elements/gvagenai`. Otherwise, or
when `metrics-manager` cannot store histograms, a performance test reports the means over every request since
the element started, read from the answers that `gvagenai` writes.

Latency metrics need the `latency_tracer`, which is on by default with `DLSPS2_OTEL=true` and:

```bash
DLSPS2_GST_TRACERS='latency_tracer(flags=pipeline,interval=1000,post-metrics=true)'
```

Tracers apply to every pipeline the server runs, so the tracer also runs for tests that do not ask for latency
metrics. To run without it, for example for FPS measurements, set it empty:

```bash
export DLSPS2_GST_TRACERS=
make run
```

Without the tracer, a test that asks for latency metrics runs without them: `vippet` logs a warning and the
job details say so. The tracer must support `post-metrics`; with an older DL Streamer no samples arrive, and
`vippet` logs a warning.

See [Known limitations of pipeline execution on DL Streamer Pipeline Server 2.0](../../troubleshooting.md#16-known-limitations-of-pipeline-execution-on-dl-streamer-pipeline-server-20).

## Optional: stream from GigE Vision cameras

The DL Streamer Pipeline Server 2.0 image does not include the Aravis GStreamer plugin (`aravissrc`), so
the `vippet` image ships it with the custom elements in `vippet/gst_plugins/`, and the server loads it from the
`vippet-gst-plugins` volume. See
[Known limitations](../../troubleshooting.md#16-known-limitations-of-pipeline-execution-on-dl-streamer-pipeline-server-20).

The `GIGE=1` flag runs the `dlstreamer-pipeline-server` container with host networking, which GigE Vision
streaming needs:

```bash
make build run GIGE=1
```

With host networking, the server's REST API listens on all host interfaces, on `DLSPS2_REST_SERVER_PORT`
(default `8081`), without authentication. Use `GIGE=1` only on a trusted network, or block that port in the host
firewall.

See [GigE Vision Cameras](../../user-guide/input-management/cameras.md#gige-vision-cameras)
for details.

## Stop the application

Stop and remove all running containers:

```bash
make stop
```

Downloaded models and videos under `shared/` are preserved. To also remove
those artifacts, run:

```bash
make clean
```
