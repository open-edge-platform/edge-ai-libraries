# Get Started

The **VLM OpenVINO serving microservice** enables support for VLM models that are not supported yet in OpenVINO model serving. This section provides step-by-step instructions to:

- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Set Environment Values

First, set the required VLM_MODEL_NAME environment variable:

```bash
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
```

Refer to [model list](./Overview.md#models-supported) for the supported models that can be used.

> **_NOTE:_** You can change the model name, model compression format, device and the number of Uvicorn workers by editing the `setup.sh` file.

### Optional: Configure OpenVINO Settings

Before sourcing the setup script, you can optionally export custom OpenVINO configuration. The `OV_CONFIG` parameter allows you to customize OpenVINO runtime behavior by passing configuration parameters as a JSON string:

```bash
# Default latency-optimized configuration (equivalent to not setting OV_CONFIG)
export OV_CONFIG='{"PERFORMANCE_HINT": "LATENCY"}'

# Throughput-optimized configuration
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT"}'

# Custom configuration with multiple streams and threads
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT", "NUM_STREAMS": 4, "INFERENCE_NUM_THREADS": 8}'

# Configuration with cache directory
export OV_CONFIG='{"PERFORMANCE_HINT": "LATENCY", "CACHE_DIR": "/tmp/ov_cache"}'
```

For a complete list of OpenVINO configuration options, refer to the [OpenVINO Documentation](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html).

### Optional: Configure Compute Device

You can specify which compute device to use for inference:

```bash
# Use CPU for inference (default)
export VLM_DEVICE=CPU

# Use GPU for inference (if available)
export VLM_DEVICE=GPU

# Use specific GPU device (if multiple GPUs available)
export VLM_DEVICE=GPU.0
export VLM_DEVICE=GPU.1

# Use integrated GPU (Intel iGPU)
export VLM_DEVICE=GPU.0

# Use discrete GPU (Intel dGPU)
export VLM_DEVICE=GPU.1
```

**Device Selection Guidelines:**

- **CPU**: Best for development, testing, and when GPU is not available. Provides consistent performance across different systems.
- **GPU**: Recommended for production workloads when GPU acceleration is available. Provides better performance for large models.
- **Multi-GPU**: When multiple GPUs are available, you can specify which one to use (e.g., `GPU.0`, `GPU.1`).

**Device Discovery:**

To see available devices on your system, you can use the `/device` endpoint after starting the service:

```bash
# Get list of available devices
curl --location --request GET 'http://localhost:9764/device'

# Get specific device details
curl --location --request GET 'http://localhost:9764/device/GPU'
```

> **Note**: When using GPU, the setup script automatically adjusts compression format to `int4` and sets workers to 1 for optimal GPU performance.

For more details about OpenVINO device selection and configuration, refer to the [OpenVINO Inference Devices Documentation](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html).

### Optional: Configure Logging Level

You can control the verbosity of logs by setting the log level:

```bash
# Set to debug for detailed logging (useful for troubleshooting)
export VLM_LOG_LEVEL=debug

# Set to info for standard logging (default)
export VLM_LOG_LEVEL=info

# Set to warning for only warnings and errors
export VLM_LOG_LEVEL=warning

# Set to error for only error messages
export VLM_LOG_LEVEL=error
```

**Log Level Details:**

- `debug`: Enables detailed logging including OpenVINO debug information. Useful for troubleshooting and development. This affects both application logs and server (Gunicorn/Uvicorn) logs.
- `info`: Standard logging level showing general operational information (default). This affects both application logs and server logs.
- `warning`: Shows only warnings and errors. This affects both application logs and server logs.
- `error`: Shows only error messages. This affects both application logs and server logs.

> **Note**: Setting `VLM_LOG_LEVEL=debug` will also enable OpenVINO debug logging, which can be very verbose but helpful for diagnosing performance and inference issues. The log level controls both the application's internal logging and the web server's logging for consistent behavior.

### Optional: Configure Access Logs

You can control where HTTP access logs (including health check requests) are written:

```bash
# Send access logs to stdout (default)
export VLM_ACCESS_LOG_FILE="-"

# Disable access logs completely (recommended for production to reduce log noise)
export VLM_ACCESS_LOG_FILE="/dev/null"

# Write access logs to a specific file
export VLM_ACCESS_LOG_FILE="/app/logs/access.log"
```

**Access Log Details:**

- **Access logs** are HTTP request logs generated by the web server (Gunicorn/Uvicorn), showing requests like health checks, API calls, etc.
- **Application logs** are logs from your Python application code, controlled by `VLM_LOG_LEVEL`
- Health check requests (`/health` endpoint) appear in access logs regardless of your application log level
- Setting `VLM_ACCESS_LOG_FILE="/dev/null"` is recommended for production to reduce log noise from health checks

> **Note**: Access logs are separate from application logs. Even if you set `VLM_LOG_LEVEL=error`, you'll still see health check requests in access logs unless you disable them with `VLM_ACCESS_LOG_FILE="/dev/null"`.

### Optional: Configure Maximum Completion Tokens

You can set a limit on the maximum number of tokens to generate:

```bash
# Set maximum completion tokens to 1000
export VLM_MAX_COMPLETION_TOKENS=1000

# Set maximum completion tokens to 500 for shorter responses
export VLM_MAX_COMPLETION_TOKENS=500
```

This parameter is useful for:

- Controlling response length
- Managing computational resources
- Ensuring consistent output sizes

### Optional: Configure Hugging Face Token

For accessing gated or private models on Hugging Face Hub, you need to set your Hugging Face token:

```bash
# Set your Hugging Face token
export HUGGINGFACE_TOKEN=hf_your_token_here
```

To obtain your Hugging Face token:

1. Visit [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) and log in
2. Create or copy your existing access token
3. Set it using the export command above

> **Note**: Only set `HUGGINGFACE_TOKEN` if you need to access gated or private models. Public models don't require authentication.

### Complete Setup Example

Here's a complete example showing how to configure all optional settings:

```bash
# Required: Set the model name
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct

# Optional: Set compute device (CPU, GPU, GPU.0, GPU.1, etc.)
export VLM_DEVICE=GPU

# Optional: Set log level (debug, info, warning, error)
export VLM_LOG_LEVEL=info

# Optional: Configure OpenVINO for throughput optimization
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT", "NUM_STREAMS": 2}'

# Optional: Set maximum completion tokens
export VLM_MAX_COMPLETION_TOKENS=1000

# Optional: Set Hugging Face token (only if needed for gated models)
export HUGGINGFACE_TOKEN=hf_your_token_here

# Run the setup script
source setup.sh
```

Set the environment with default values by running the following script:

```bash
source setup.sh
```

The server takes the runtime values from .env file

- `http_proxy`: Specifies the HTTP proxy server URL to be used for HTTP requests.
- `https_proxy`: Specifies the HTTPS proxy server URL to be used for HTTPS requests.
- `no_proxy_env`: A comma-separated list of domain names or IP addresses that should bypass the proxy.
- `VLM_MODEL_NAME`: The name or path of the model to be used, e.g., `microsoft/Phi-3.5-vision-instruct`.
- `VLM_COMPRESSION_WEIGHT_FORMAT`: Specifies the format for compression weights, e.g., `int4`.
- `VLM_DEVICE`: Specifies the compute device to use for inference. Supported values include `CPU` (default), `GPU`, `GPU.0`, `GPU.1`, etc. When set to `GPU`, the system will automatically optimize settings for GPU inference. For multi-GPU systems, specify the device index (e.g., `GPU.0` for first GPU, `GPU.1` for second GPU). See [OpenVINO Inference Devices](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html) for more details.
- `VLM_SERVICE_PORT`: The port number on which the FastAPI server will run, e.g., `9764`.
- `TAG`[Optional]: Specifies the tag for the Docker image, e.g., `latest`.
- `REGISTRY`[Optional]: Specifies the Docker registry URL.
- `VLM_SEED` [Optional]: An optional environment variable used to set the seed value for deterministic behavior in the VLM inference Serving. This can be useful for debugging or reproducing results. If not provided, a random seed will be used by default.
- `VLM_LOG_LEVEL` [Optional]: Sets the logging level for the VLM service. Accepted values are `debug`, `info`, `warning`, `error`. If not provided, defaults to `info`. When set to `debug`, it also enables detailed OpenVINO logging.
- `VLM_MAX_COMPLETION_TOKENS` [Optional]: Sets the maximum number of tokens to generate in the completion. If not provided, the model will use its default maximum. This can be useful for controlling response length and managing computational resources.
- `HUGGINGFACE_TOKEN` [Optional]: Required for accessing gated or private models on Hugging Face Hub. Some models require authentication to download. If not provided, only public models will be accessible.
- `OV_CONFIG` [Optional]: A JSON string containing OpenVINO configuration parameters. Common parameters include `PERFORMANCE_HINT` (LATENCY/THROUGHPUT), `NUM_STREAMS`, `INFERENCE_NUM_THREADS`, `CACHE_DIR`, etc. If not provided, defaults to `{"PERFORMANCE_HINT": "LATENCY"}`.

### Environment Variables Usage Examples

#### Basic Usage (Default Settings)

```bash
# Minimal setup - only required variable
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
source setup.sh
```

#### Performance Optimization

```bash
# Configure for maximum throughput
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT"}'
source setup.sh
```

#### GPU Acceleration

```bash
# Use GPU for better performance
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_DEVICE=GPU
source setup.sh
```

#### Multi-GPU Setup

```bash
# Use specific GPU device
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_DEVICE=GPU.0
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT"}'
source setup.sh
```

#### Response Length Control

```bash
# Limit response length
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_MAX_COMPLETION_TOKENS=500
source setup.sh
```

#### Debug Mode Setup

```bash
# Enable debug logging for troubleshooting
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_LOG_LEVEL=debug
source setup.sh
```

#### Gated Model Access

```bash
# Access gated models from Hugging Face
export VLM_MODEL_NAME=microsoft/Phi-3.5-vision-instruct
export HUGGINGFACE_TOKEN=hf_your_token_here
source setup.sh
```

#### Complete Configuration

```bash
# Full configuration example with GPU acceleration
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_DEVICE=CPU
export VLM_LOG_LEVEL=info
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT"}'
export VLM_MAX_COMPLETION_TOKENS=1000
export HUGGINGFACE_TOKEN=hf_your_token_here
source setup.sh
```

## Quick Start with Docker

The user has an option to either [build the docker images](./how-to-build-from-source.md#steps-to-build) or use prebuilt images as documented below.

_Document how to get prebuilt docker image_

## Running the Server with CPU

To run the server using Docker Compose, use the following command:

```bash
docker compose up -d
```

## Running the Server with GPU

To run the server with GPU acceleration, follow these steps:

### 1. Configure GPU Device

Configure your GPU device using the instructions in the [Configure Compute Device](#optional-configure-compute-device) section above. For GPU setup:

```bash
# For single GPU or automatic GPU selection
export VLM_DEVICE=GPU

# For specific GPU device (if multiple GPUs available)
export VLM_DEVICE=GPU.0  # Use first GPU
export VLM_DEVICE=GPU.1  # Use second GPU
```

### 2. Run Setup Script

```bash
source setup.sh
```

> **Note**: When `VLM_DEVICE=GPU` is set, the setup script automatically optimizes settings for GPU performance (changes compression format to `int4` and sets workers to 1).

### 3. Start the Service

```bash
docker compose up -d
```

### 4. Verify GPU Configuration

After starting the service, verify your GPU setup:

```bash
# Check service health
curl --location --request GET 'http://localhost:9764/health'

# Check available devices and current configuration
curl --location --request GET 'http://localhost:9764/device'
```

For detailed GPU configuration options, device discovery, and performance tuning recommendations, refer to the [Configure Compute Device](#optional-configure-compute-device) section above.

## Sample CURL Commands

### Test with Image URL

```bash
curl --location 'http://localhost:9764/v1/chat/completions' \
--header 'Content-Type: application/json' \
--data '{
    "model": "microsoft/Phi-3.5-vision-instruct",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Describe the activities and events captured in the image. Provide a detailed description of what is happening. While referring to an object or person or entity, identify them as uniquely as possible such that it can be tracked in future. Keep attention to detail, but avoid speculation or unnecessary attribution of details."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://github.com/openvinotoolkit/openvino_notebooks/assets/29454499/d5fbbd1a-d484-415c-88cb-9986625b7b11"
                    }
                }
            ]
        }
    ],
    "max_completion_tokens": 500,
    "temperature": 0.1,
    "top_p": 0.3,
    "frequency_penalty": 1
}'
```

### Test with Base64 Image

```bash
curl --location 'http://localhost:9764/v1/chat/completions' \
--header 'Content-Type: application/json' \
--data '{
    "model": "microsoft/Phi-3.5-vision-instruct",
    "max_completion_tokens": 100,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Describe this image."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64,<base64 image value>"
                    }
                }
            ]
        }
    ]
}'
```

### Test with Multiple Images

```bash
curl --location 'http://localhost:9764/v1/chat/completions' \
--header 'Content-Type: application/json' \
--data '{
    "model": "microsoft/Phi-3.5-vision-instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "Describe these image. Generate the output in json format as {image_1:Description1, image_2:Description2}"
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://preschool.org/wp-content/uploads/2021/08/What-to-do-during-your-preschool-reading-time-855x570.jpg"
            }
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://images.squarespace-cdn.com/content/v1/659e1d627cfb464f89ed5d6d/16cb28f5-86eb-4bdd-a240-fb3316523aee/AdobeStock_663850233.jpeg"
            }
          }
        ]
      }
    ],
    "max_completion_tokens": 200
  }'
```

### Test continuous chat

- Method 1 (using curl call):

    ```bash

    curl --location 'http://localhost:9764/v1/chat/completions' \
    --header 'Content-Type: application/json' \
    --data '{
        "model": "microsoft/Phi-3.5-vision-instruct",
        "messages": [
        {
            "role": "user",
            "content": "Describe this video and remember this number: 4245"
        },
        {
            "role": "assistant",
            "content": "The video appears to be taken at night, as indicated by the darkness and artificial lighting. The timestamp on the video suggests it was recorded early in the morning on August 25, 2024, in the Eastern Time Zone (ET). The camera is labeled indicates that it is a body-worn camera used by law enforcement.\n\nThe scene shows a sidewalk bordered by a metal fence on both sides. There are trees lining the sidewalk, and some people can be seen walking in the distance. In the background, there are parked cars and what appears to be a building with illuminated windows. The overall atmosphere seems calm, with no immediate signs of distress or urgency.\n\nRemember the number: 4245"
        },
        {
            "role": "user",
            "content": "What is the number ?"
        }
        ],
        "max_completion_tokens": 1000
    }'
    ```

- Method 2 (using openai python client):

    ```python
    from openai import OpenAI

    client = OpenAI(
        base_url = "http://localhost:9764/v1",
        api_key="",
    )

    # Define the conversation history
    messages = [
        {
            "role": "user",
            "content": "Describe this video and remember this number: 4245"
        },
        {
            "role": "assistant",
            "content": "The video appears to be taken at night, as indicated by the darkness and artificial lighting. The timestamp on the video suggests it was recorded early in the morning on August 25, 2024, in the Eastern Time Zone (ET). The camera is labeled indicates that it is a body-worn camera used by law enforcement.\n\nThe scene shows a sidewalk bordered by a metal fence on both sides. There are trees lining the sidewalk, and some people can be seen walking in the distance. In the background, there are parked cars and what appears to be a building with illuminated windows. The overall atmosphere seems calm, with no immediate signs of distress or urgency.\n\nRemember the number: 4245"
        },
        {
            "role": "user",
            "content": "What did I ask you to do? What is the number?"
        }
    ]

    # Send the request to the model
    response = client.chat.completions.create(
        model="microsoft/Phi-3.5-vision-instruct",
        messages=messages,
        max_completion_tokens=1000,
    )
    # Print the model's response
    print(response.choices[0].message.content)
    ```

### Test **video** type input

> **_NOTE:_** video_url type input is only supported with the `Qwen/Qwen2.5-VL-7B-Instruct` or `Qwen/Qwen2-VL-2B-Instruct` models. Although other models will accept input as `video` type, but internally they will process it as multi-image input only.

```bash
curl --location 'http://localhost:9764/v1/chat/completions' \
--header 'Content-Type: application/json' \
--data '{
    "model": "microsoft/Phi-3.5-vision-instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "Consider these images as frames of single video. Describe this video and sequence of events."
          },
          {
            "type": "video",
            "video": [
                "http://localhost:8080/chunk_6_frame_3.jpeg",
                "http://localhost:8080/chunk_6_frame_4.jpeg"
            ]
          }
        ]
      }
    ],
    "max_completion_tokens": 1000
  }'
```

### Test **video_url** type input

> **_NOTE:_** video_url type input is only supported with the `Qwen/Qwen2.5-VL-7B-Instruct` or `Qwen/Qwen2-VL-2B-Instruct` models.
> **_NOTE:_** `max_pixels` and `fps` are optional parameters.

```bash
curl --location 'http://localhost:9764/v1/chat/completions' \
--header 'Content-Type: application/json' \
--data '{
    "model": "Qwen/Qwen2.5-VL-7B-Instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "Describe this video"
          },
          {
            "type": "video_url",
            "video_url": {
              "url": "http://localhost:8080/original-1sec.mp4"
            },
            "max_pixels": "360*420",
            "fps": 1
          }
        ]
      }
    ],
    "max_completion_tokens": 1000,
    "stream":true
  }'
```

### Test **video_url** as base64 encoded video input

> **_NOTE:_** video_url type input is only supported with the `Qwen/Qwen2.5-VL-7B-Instruct` or `Qwen/Qwen2-VL-2B-Instruct` models.
> **_NOTE:_** `max_pixels` and `fps` are optional parameters.

```bash
curl --location 'http://localhost:9764/v1/chat/completions' \
--header 'Content-Type: application/json' \
--data '{
    "model": "Qwen/Qwen2.5-VL-7B-Instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "Describe this video"
          },
          {
            "type": "video_url",
            "video_url": {
              "url": "data:video/mp4;base64,{video_base64}"
            }
          }
        ]
      }
    ],
    "max_completion_tokens": 1000,
    "stream":true
  }'
```

### Test GET Device

To get the list of available devices

```bash
curl --location --request GET 'http://localhost:9764/device'
```

### Test POST Device details

To get specific device details

```bash
curl --location --request POST 'http://localhost:9764/device?device=GPU' \
--header 'Content-Type: application/json'
```

## Running Tests and Generating Coverage Report

To ensure the functionality of the microservice and measure test coverage, follow these steps:

1. **Install Dependencies**  
   Install the required dependencies, including development dependencies, using:

   ```bash
   poetry install --with test
   ```

2. **Run Tests with Poetry**  
   Use the following command to run all tests:

   ```bash
   poetry run pytest
   ```

3. **Run Tests with Coverage**  
   To collect coverage data while running tests, use:

   ```bash
   poetry run coverage run --source=src -m pytest
   ```

4. **Generate Coverage Report**  
   After running the tests, generate a coverage report:

   ```bash
   poetry run coverage report -m
   ```

5. **Generate HTML Coverage Report (Optional)**  
   For a detailed view, generate an HTML report:

   ```bash
   poetry run coverage html
   ```

   Open the `htmlcov/index.html` file in your browser to view the report.

These steps will help you verify the functionality of the microservice and ensure adequate test coverage.

## Troubleshooting

1. **Docker Container Fails to Start**:
    - Run `docker logs {{container-name}}` to identify the issue.
    - Check if the required port is available.


2. **Cannot Access the Microservice**:
    - Confirm the container is running:
      ```bash
      docker ps
      ```

## Supporting Resources

* [Overview](Overview.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
