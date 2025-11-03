# Get Started

The **Multi-level Video Understanding Microservice** enables developers to create video summary from video files. This section provides step-by-step instructions to:

- Set up dependent microservices of genai model servings, including large language models(llms) and vision language models(vlms).
- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Setup GenAI Model Servings for VLM and LLM

This microservice is designed to work effortlessly with GenAI model servings that provide OpenAI-compatible APIs. We recommend take **vLLM-IPEX** as an example, this is primarily used for inference on Intel single-GPU or multiple-GPUs, optimized for Intel® Arc™ Pro B60 Graphics.

**step1.** Prepare GenAIComps from Open Platform for Enterprise AI (OPEA):
```bash
git clone https://github.com/opea-project/GenAIComps.git
cd GenAIComps
```

**step2.** Start model serving for VLM
Following the tutorial in [LVM Microservice with vLLM on Intel XPU](https://opea-project.github.io/latest/GenAIComps/comps/lvms/src/README_vllm_ipex.html)

**Key Configuration**
- `MAX_MODEL_LEN`: max model length, constraints to GPU memory.
- `LLM_MODEL_ID`: huggingface model id.
- `LOAD_QUANTIZATION`: model precision.
- `VLLM_PORT`: LLM model serving port.
- `ONEAPI_DEVICE_SELECTOR`: device id, use `export ONEAPI_DEVICE_SELECTOR=level_zero:[gpu_id];level_zero:[gpu_id]` to select device before excuting your command.
- `TENSOR_PARALLEL_SIZE`: tensor parallel size.

An example that has been verified by this microservice:
```bash
export MAX_MODEL_LEN=20000
export LLM_MODEL_ID=Qwen/Qwen2.5-VL-7B-Instruct
export LOAD_QUANTIZATION=fp8
export VLLM_PORT=41091
export ONEAPI_DEVICE_SELECTOR="level_zero:0;level_zero:0"
export TENSOR_PARALLEL_SIZE=2
```

Then, check existence of serving:
```bash
docker logs -f lvm-vllm-ipex-service

...
INFO:     Started server process [411]
INFO:     Waiting for application startup.
INFO:     Application startup complete.

```

**step3.** Start model serving for LLM
Following the tutorial in [LLM Microservice with vLLM on Intel XPU](https://opea-project.github.io/latest/GenAIComps/comps/llms/src/text-generation/README_vllm_ipex.html)


**Key Configuration**
- `MAX_MODEL_LEN`: max model length, constraints to GPU memory.
- `LLM_MODEL_ID`: huggingface model id.
- `LOAD_QUANTIZATION`: model precision.
- `VLLM_PORT`: LLM model serving port.
- `ONEAPI_DEVICE_SELECTOR`: device id, use `export ONEAPI_DEVICE_SELECTOR=level_zero:[gpu_id];level_zero:[gpu_id]` to select device before excuting your command.
- `TENSOR_PARALLEL_SIZE`: tensor parallel size.

An example that has been verified by this microservice:
```bash
export MAX_MODEL_LEN=20000
export LLM_MODEL_ID=Qwen/Qwen3-32B-AWQ
export LOAD_QUANTIZATION=awq
export VLLM_PORT=41090
export ONEAPI_DEVICE_SELECTOR="level_zero:2;level_zero:3"
export TENSOR_PARALLEL_SIZE=2
```

Then, check existence of serving:
```bash
docker logs -f textgen-vllm-ipex-service

...
INFO:     Started server process [411]
INFO:     Waiting for application startup.
INFO:     Application startup complete.

```

> Note: Please refer to [validated models](./Overview.md#validated-models) for the list of models that can has been verified in video summarization.


## Quick Start with Docker

**step1.** Prepare docker image
Before lauching the service as documented below, users need to prepare the docker images:

- **Option1.** [build the docker images](./how-to-build-from-source.md#steps-to-build)
- **Option2.** Download the prebuilt images from Docker Hub (Link TBD)

Then, use the following commands to set up the `multilevel-video-understanding` microservice.

**step2.** Set up environment variables

The following environment variables can be configured:

**Basic configuration**
- `REGISTRY_URL`: Docker image registry url (default: intel/)
- `TAG`: Docker image tag (default: latest)
- `SERVICE_PORT`: Multi-level Video Understanding Microservice port (default: 8192)
- `MAX_CONCURRENT_REQUESTS`: Max concurrent requests for this microservice (default: 6)
- `DEBUG`: Enable debug mode (default: False)

**Model configuration**
- `VLM_MODEL_NAME`: Vison-Language model(VLM), this should comply with model serving's `model` field.
- `VLM_BASE_URL`: Model serving's base url for VLM. (e.g., `http://localhost:41091/v1`)
- `LLM_MODEL_NAME`: Large Language model(LLM), this should comply with model serving's `model` field.
- `LLM_BASE_URL`: Model serving's base url for LLM. (e.g., `http://localhost:41090/v1`)

**Example of minimum required environment variables**
```bash
export REGISTRY_URL=intel/
export TAG=latest
export VLM_BASE_URL="http://<model-serving-ip-address>:41091/v1"
export LLM_BASE_URL="http://<model-serving-ip-address>:41090/v1"
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-7B-Instruct
export LLM_MODEL_NAME=Qwen/Qwen3-32B-AWQ
```
> **Note:** Please remember to change `REGISTRY_URL` and `TAG` as needed. 
> - If `REGISTRY_URL` is provided, the final image name will be: `${REGISTRY_URL}/multilevel-video-understanding:${TAG}`.
> - If `REGISTRY_URL` is not provided, the image name will be: `multilevel-video-understanding:${TAG}`

**step3.** Launch the microservice
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
cd edge-ai-libraries/microservices/multilevel-video-understanding
chmod +x ./setup_docker.sh
./setup_docker.sh
```

Once the service is up, you can check the log:
```bash
$ docker ps

CONTAINER ID   IMAGE                                         PORTS                                         NAMES
6f00712bf4b6   intel/multilevel-video-understanding:latest   0.0.0.0:8192->8000/tcp, [::]:8192->8000/tcp   docker-multilevel-video-understanding-1

# the container name may change depend to your runtime
$ docker logs -f docker-multilevel-video-understanding-1

INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

```

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
    "processor_kwargs": {"process_fps": 1}
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

```
http://localhost:8192/docs
```

## Manual Host Setup using Poetry

1. Clone the repository and change directory to the audio-analyzer microservice:
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
cd edge-ai-libraries/microservices/multilevel-video-understanding
```

2. Install Poetry if not already installed.
```bash
pip install poetry==1.8.3
```

3. Configure poetry to create a local virtual environment.
```bash
poetry config virtualenvs.create true
poetry config virtualenvs.in-project true
```

4. Install dependencies:
```bash
poetry lock --no-update
poetry install
```

5. Install video-chunking-utils from OEP/EAL source
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
cd edge-ai-libraries/libraries/video-chunking-utils
pip install .
```

6. Set the environment variables as needed:
```bash
export VLM_BASE_URL="http://<model-serving-ip-address>:41091/v1"
export LLM_BASE_URL="http://<model-serving-ip-address>:41090/v1"
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-7B-Instruct
export LLM_MODEL_NAME=Qwen/Qwen3-32B-AWQ
export SERVICE_PORT=8192
```

7. Run the service:
```bash
DEBUG=True poetry run uvicorn video_analyzer.main:app --host 0.0.0.0 --port ${SERVICE_PORT} --reload
```

<!-- ## Troubleshooting -->


## Supporting Resources

* [Overview](Overview.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
