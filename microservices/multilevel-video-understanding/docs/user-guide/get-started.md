# Get Started

The **Multi-level Video Understanding Microservice** enables developers to create video summaries from video files (especially long videos). This section provides step-by-step instructions to:

- Set up an on-device GenAI model serving (VLM + LLM) that exposes an OpenAI-compatible API.
- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- **GPU Driver Installed**: This guide assumes the GPU driver on the target machine is already installed. If it is not, install the Intel GPU driver packages by following the official [Installing Packages from the Intel PPA](https://dgpu-docs.intel.com/installation-guides/installing-packages-from-the-intel-ppa.html) guide first.
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## On-device AI Services

In the reference deployment, both the model serving and this microservice run **locally on a single Intel® Core™ Ultra (Panther Lake, PTL) host**, with the integrated GPU sharing system RAM — no discrete accelerator or remote inference cluster is required.

This microservice is designed to work effortlessly with GenAI model servings that provide OpenAI-compatible APIs. We recommend take **vLLM-IPEX** as an example. A single Mixture-of-Experts model, **Qwen3.5-35B-A3B** (35B total / 3B active), serves both the **VLM** role (per-chunk captioning) and the **LLM** role (hierarchical aggregation) from one endpoint.

> **Platform note:** This guide is written around the **on-device PTL iGPU** profile, where the serving and the microservice share one host. Only the vLLM-IPEX serving ([llm-scaler](https://github.com/intel/llm-scaler)) is platform-sensitive. To run on a discrete-GPU host such as **Intel® Arc™ Pro B60** instead, deploy vLLM-IPEX on that machine (serving `Qwen3.5-35B-A3B` may require multiple GPUs)。

### Memory & swap requirements

`Qwen3.5-35B-A3B` in FP8 with a 60k context window is memory-hungry on a shared-RAM host. The default configuration targets a **64 GB system**:

- Provide at least **32 GB of swap** so the weight load and KV cache can spill under peak pressure without the OOM killer stepping in. If your host lacks enough swap, see [Adding Swap Space](./get-started/add-swap.md).
- To lower the footprint, reduce `MAX_MODEL_LEN` (e.g. `32768`) or switch `LOAD_QUANTIZATION` to `awq` / `sym_int4` in [set_env.sh](../../docker/set_env.sh).
- The **first startup takes 3–20 minutes** while the weights are downloaded and compiled. The serving becomes healthy once it answers on `http://<host>:41091/v1/models`.

## Step 1. Configure the environment

All environment variables for both the model serving and the microservice live in one file, [docker/set_env.sh](../../docker/set_env.sh). Source it in your shell before starting anything:

```bash
cd edge-ai-libraries/microservices/multilevel-video-understanding
source docker/set_env.sh
```

**Key variables**

Model serving (vLLM-IPEX):

- `LLM_MODEL`: model served for both roles (default `Qwen/Qwen3.5-35B-A3B`).
- `MAX_MODEL_LEN`: context window; drives KV-cache memory (default `61440` = 60k).
- `LOAD_QUANTIZATION`: precision — `fp8` (default), `awq`, or `sym_int4`.
- `GPU_MEM_UTIL`: fraction of shared system RAM the serving may reserve (`0.7` for fp8, `0.5` for awq/sym_int4).
- `VLLM_SERVICE_PORT`: OpenAI-compatible serving port (default `41091`).

Microservice:

- `VLM_MODEL_NAME` / `LLM_MODEL_NAME`: must match the served model name (both default to `LLM_MODEL`).
- `VLM_BASE_URL` / `LLM_BASE_URL`: OpenAI-compatible endpoints (both default to the on-device serving).
- `SERVICE_PORT`: microservice port (default `8192`).
- `MAX_CONCURRENT_REQUESTS`: max concurrent inference requests (default `4`).
- `VIDEO_SUMMARY_CACHE_HOST`: host directory for the runtime prompt-registry cache. Must exist as a user-owned directory before `docker compose up` (the script creates it for you).

## Step 2. Prepare the microservice image

Provide the `multilevel-video-understanding` image in one of two ways:

- **Option 1.** [Build the docker image](./get-started/build-from-source.md#steps-to-build)
- **Option 2.** Download the prebuilt image from Docker Hub ([intel/multilevel-video-understanding](https://hub.docker.com/r/intel/multilevel-video-understanding))

  ```bash
  docker pull intel/multilevel-video-understanding:2026.2.0
  ```

> **Note:** If `REGISTRY_URL` is provided, the final image name is `${REGISTRY_URL}/multilevel-video-understanding:${TAG}`; otherwise it is `multilevel-video-understanding:${TAG}`.

## Step 3. Launch

The Compose file ([docker/compose.yaml](../../docker/compose.yaml)) defines both services on a shared network: `vllm-ipex-serving` (the model serving) and `multilevel-video-understanding`. Choose one of the two deployment options below.

```bash
chmod +x ./setup_docker.sh
```

### Option 1 — End-to-end (bundled model serving)

Start **both** the on-device model serving and the microservice together. This is the default. Compose pulls the `vllm-ipex-serving` image (`intel/llm-scaler-vllm`) automatically, and the microservice `depends_on` the serving being **healthy**, so on the first run Compose waits while the model downloads and compiles (the 3–20 minute step).

```bash
./setup_docker.sh            # or: ./setup_docker.sh --prod
```

### Option 2 — Use an existing model serving

If you already have an OpenAI-compatible serving running — a **warm local `vllm-ipex-serving`** (fast iteration on the same host) or a **remote** endpoint — point the microservice at it in [docker/set_env.sh](../../docker/set_env.sh) and start with `--light`:

```bash
# in docker/set_env.sh (or your shell), set the endpoint(s), e.g. a remote host:
export VLM_BASE_URL=http://<serving-host>:41091/v1
export LLM_BASE_URL=http://<serving-host>:41091/v1

source docker/set_env.sh
./setup_docker.sh --light
```

`--light` health-checks the configured endpoint (`VLM_BASE_URL` / `LLM_BASE_URL`); if it is already serving a model, only `multilevel-video-understanding` is started (the serving is never touched). For a **local** endpoint that is not yet healthy, `--light` transparently falls back to the full end-to-end start; for a **remote** endpoint it starts the microservice anyway and lets it retry at runtime.

Check the status and logs:

```bash
docker ps
```

```text
CONTAINER ID   IMAGE                                          PORTS                                         NAMES
a1b2c3d4e5f6   intel/llm-scaler-vllm:0.14.0-b7.1              0.0.0.0:41091->8000/tcp                       vllm-ipex-serving
6f00712bf4b6   intel/multilevel-video-understanding:2026.2.0    0.0.0.0:8192->8000/tcp, [::]:8192->8000/tcp   docker-multilevel-video-understanding-1
```

```bash
# Follow the model-serving startup (weights download + compile on first run):
docker logs -f vllm-ipex-serving        # ready when it serves /v1/models
# Then the microservice:
docker logs -f docker-multilevel-video-understanding-1
```

```text
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

(In Option 2 only the `multilevel-video-understanding` container is started.)

To stop everything: `./setup_docker.sh --down`.

> **Note:** `--light` is the equivalent of `docker compose up -d --no-deps multilevel-video-understanding` plus a readiness probe of the configured endpoint — use the raw command if you prefer to manage the serving entirely yourself.

## Microservice Usage Examples

Below are examples of how to use the API with curl.

### Health Check

Health check endpoint.
**Returns:**  A response indicating the service status, version and a descriptive message.

```bash
curl -X GET "http://localhost:8192/v1/health"
```

### Get Available Models

Get a list of available model variants that are configured for summarization.
**Returns:** A response with the list of available models with their details and the default model

```bash
curl -X GET "http://localhost:8192/v1/models"
```

### Request video summarization

Generate a summary text from a video file to describe its content.
**Returns:** A response with the processing status and summary output

```bash
curl http://localhost:8192/v1/summary -H "Content-Type: application/json" -d '{
    "video": "https://videos.pexels.com/video-files/5992517/5992517-hd_1920_1080_30fps.mp4",
    "method": "USE_ALL_T-1",
    "processor_kwargs": {"levels": 4, "level_sizes": [1,6,8,-1], "process_fps": 1}
}'
```

Response example:

```json
{
  "status":"completed",
  "summary":"The video presents xxx",
  "job_id":"37a09a31",
  "video_name":"https://videos.pexels.com/video-files/5992517/5992517-hd_1920_1080_30fps.mp4",
  "video_duration":55.6
}
```

This API endpoint returns a video summary, job ID, and other details once the summarization is done.

## API Documentation

When running the service, you can access the Swagger UI documentation at:

```bash
http://localhost:8192/docs
```

## Manual Host Setup using Poetry

1. Clone the repository and change directory to the `multilevel-video-understanding` microservice:

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b main
   cd edge-ai-libraries/microservices/multilevel-video-understanding
   ```

2. Install Poetry if not already installed.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install poetry==1.8.3
   ```

3. Install dependencies:

   ```bash
   poetry lock --no-update
   poetry install
   ```

   > **Note:** sometimes `poetry install` may take a long time; in that case, an alternative option to install packages could be:
   >
   > ```bash
   > poetry export -f requirements.txt > requirements.txt
   > pip install -r requirements.txt
   > ```

4. Install video-chunking-utils from OEP/EAL source

   ```bash
   pip install ../../libraries/video-chunking-utils/
   ```

5. Set the environment variables. The simplest way is to reuse the deployment env file (it also works for a host run):

   ```bash
   source docker/set_env.sh
   ```

   > **Note:** Ensure `VLM_MODEL_NAME` / `LLM_MODEL_NAME` match the served model and `VLM_BASE_URL` / `LLM_BASE_URL` point at your on-device serving.

6. Run the service:

   ```bash
   DEBUG=True poetry run uvicorn video_analyzer.main:app --host 0.0.0.0 --port ${SERVICE_PORT} --reload
   ```

<!-- ## Troubleshooting -->

## Supporting Resources

- [Overview](./index.md)
- [API Reference](./api-reference.md)
- [System Requirements](./get-started/system-requirements.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements
./get-started/build-from-source

:::
hide_directive-->
