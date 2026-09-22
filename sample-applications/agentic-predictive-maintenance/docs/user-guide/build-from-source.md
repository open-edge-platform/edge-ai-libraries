# How to Build from Source

This guide explains how to build the APM blueprint's application images from source code.

> **Note**: Building from source is only needed if you want to customize the application code. For standard deployments, the prebuilt images referenced in the Docker Compose files are sufficient.

## Prerequisites

1. Complete the steps in the [Get Started](./get-started.md) guide.
2. Ensure Docker and Docker Compose are installed and the Docker daemon is running.
3. If building behind a proxy, set `http_proxy`, `https_proxy`, and `no_proxy` in your shell before running any build commands.

## Steps to Build from Source

### 1. Clone the Repository

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/sample-applications/agentic-predictive-maintenance
```

### 2. Configure the Build

Set the registry URL and tag for the images you want to build. If you leave `REGISTRY` empty, images will be built and tagged locally.

```bash
export REGISTRY=            # e.g. "docker.io/myusername/" — leave empty for local builds
export TAG=latest
```

### 3. Build the Images

The `Makefile` provides build targets for each service and for all services together.

**Build all three application services:**

```bash
make build
```

**Build individual services:**

```bash
make build-storage   # storage-service only
make build-agents    # agent-service only
make build-ui        # ui-service only
```

The build targets use the Dockerfiles located in `services/<service-name>/Dockerfile`.

### 4. Verify the Build

After the build completes, confirm the images are present:

```bash
docker images | grep apm
```

You should see entries for `apm-storage-service`, `apm-agent-service`, and `apm-ui-service`.

### 5. Deploy with Local Images

Run the setup script normally. It will use the locally built images when the `REGISTRY` variable is empty:

```bash
./setup.sh --use-case pipeline-defect-detection
```

## Reused Microservices

The following microservices are reused from the `edge-ai-libraries` microservices catalog and are pulled as prebuilt images — they are not built by the APM `Makefile`:

| Microservice | Image |
|---|---|
| DL Streamer Pipeline Server | `intel/dlstreamer-pipeline-server` |
| VLM OpenVINO Serving | `intel/vlm-openvino-serving` |
| Model Download | `intel/model-download` |

To customize these microservices, refer to their respective source directories under `microservices/` in the `edge-ai-libraries` repository.
