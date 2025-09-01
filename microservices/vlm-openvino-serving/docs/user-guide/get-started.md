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

### Optional Environment Variables

The VLM OpenVINO Serving microservice supports many optional environment variables for customizing behavior, performance, and logging. For complete details on all available environment variables, including examples and advanced configurations, see the [Environment Variables Guide](./environment-variables.md).

**Quick Configuration Examples**:

```bash
# Basic CPU setup (default)
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct

# GPU acceleration
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_DEVICE=GPU

# Performance optimization
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT"}'

# Production setup with clean logging
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_LOG_LEVEL=warning
export VLM_ACCESS_LOG_FILE="/dev/null"
```

**Key Environment Variables**:

- **VLM_DEVICE**: Set to `CPU` (default) or `GPU` for device selection
- **OV_CONFIG**: JSON string for OpenVINO performance tuning
- **VLM_LOG_LEVEL**: Control logging verbosity (`debug`, `info`, `warning`, `error`)
- **VLM_MAX_COMPLETION_TOKENS**: Limit response length
- **HUGGINGFACE_TOKEN**: Required for gated models

For detailed information about each variable, configuration examples, and advanced setups, refer to the [Environment Variables Guide](./environment-variables.md).

Set the environment with default values by running the following script:

```bash
source setup.sh
```

> **_NOTE:_** For a complete reference of all environment variables, their descriptions, and usage examples, see the [Environment Variables Guide](./environment-variables.md).

## Quick Start with Docker

The user has an option to either [build the docker images](./how-to-build-from-source.md#steps-to-build) or use prebuilt images as documented below.

_Document how to get prebuilt docker image_

## Running the Server with CPU

To run the server using Docker Compose, use the following command:

```bash
docker compose -f docker/compose.yaml up -d
```

## Running the Server with GPU

To run the server with GPU acceleration, follow these steps:

### 1. Configure GPU Device

Configure your GPU device using the instructions in the `Device Configuration` section in [Environment Variables Guide](./environment-variables.md#device-configuration). For GPU setup:

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
docker compose -f docker/compose.yaml up -d
```

### 4. Verify GPU Configuration

After starting the service, verify your GPU setup:

```bash
# Check service health
curl --location --request GET 'http://localhost:9764/health'

# Check available devices and current configuration
curl --location --request GET 'http://localhost:9764/device'
```

For detailed GPU configuration options, device discovery, and performance tuning recommendations, refer to the `Device Configuration` section in [Environment Variables Guide](./environment-variables.md#device-configuration).

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

- [Overview](Overview.md)
- [Environment Variables Guide](environment-variables.md)
- [API Reference](api-reference.md)
- [System Requirements](system-requirements.md)
