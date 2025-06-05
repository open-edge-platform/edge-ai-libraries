# VLM(Visual Language Model) Inference Microservice

FastAPI server wrapping OpenVINO runtime to serve OpenAI style `/v1/chat/completion` endpoint, to consume user input as multi-modality of image and video inputs and serve inference with VLM models.

## Index

- [Prerequisites](#-prerequisites)
- [Repository Structure](#repository-structure)
- [Building CPU Docker Image](#building-cpu-docker-image)
- [Building GPU Docker Image](#building-gpu-docker-image)
- [Running the Server with CPU](#running-the-server-with-cpu)
- [Running the Server with GPU](#running-the-server-with-gpu)
- [Supported Models](#supported-models)
- [Sample CURL Commands](#sample-curl-commands)
- [Running Tests and Generating Coverage Report](#running-tests-and-generating-coverage-report)

## Repository Structure

```plaintext
vlm-inference-microservice/ 
── README.md 
├── .dockerignore 
├── .env 
├── .gitignore 
├── logging.comf
├── poetry.lock
├── pyproject.toml 
├── compose.yaml 
├── compose.gpuyaml 
├── app.py 
├── utils/ 
│   ├── init.py 
│   ├── common.py 
│   ├── utils.py
├── docker/
│   ├── Dockerfile 
│   ├── Dockerfile.gpu
├── scripts/
│   ├── install_ubuntu_gpu_drivers.sh 
│   ├── compress_model.sh
```

## 📄 Prerequisites

- Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Docker Compose: [Installation Guide](https://docs.docker.com/compose/install/).

**_(Optional)_** Docker Compose builds the _VLM Inference Microservice_ with a default image and tag name. If you want to use a different image and tag, export these variables:

  ```bash
    export REGISTRY_URL="your_container_registry_url"
    export PROJECT_NAME="your_project_name"
    export TAG="your_tag"
  ```

> **_NOTE:_** `PROJECT_NAME` will be suffixed to `REGISTRY_URL` to create a namespaced url. Final image name will be created/pulled by further suffixing the application name and tag with the namespaced url.
> **_EXAMPLE:_** If variables are set using above command, the final image names for _Video Summary Reference Application_ would be `<your-container-registry-url>/<your-project-name>/intel-egai-vlm-inference-microservice:<your-tag>`. If variables are not set, in that case, the `TAG` will have default value as _latest_. Hence, final image will be : `intel-egai-vlm-inference-microservice:latest`.

## Generate .env file

Generate the `.env` file with default values by running the following script:
> **_NOTE:_** You can change the model name, model compression format, device and the number of Uvicorn workers by editing the `setup.sh` file.

```bash
chmod +x setup.sh
source setup.sh
```

## Building CPU Docker Image

To build the Docker image, run the following command:

```bash
docker compose build
```

## Building GPU Docker Image

To build the GPU Docker image, run the following command:

```bash
docker compose -f compose.gpu.yaml build
```

## Running the Server with CPU

To run the server using Docker Compose, use the following command:

```bash
docker compose up -d
```

## Running the Server with GPU

See the `/device` `GET` endpoint to fetch the GPU device name. If multiple GPUs are available then we have to pass like `GPU.0`. If only one GPU device is present the we can pass `GPU`.
Change the `VLM_DEVICE=GPU` in `setup.sh` script and run it again.

To run the server using the GPU Docker Compose file, use the following command:

```bash
docker compose -f compose.gpu.yaml up -d
```

### .env file parameters

The server takes the runtime values from .env file

- `http_proxy`: Specifies the HTTP proxy server URL to be used for HTTP requests.
- `https_proxy`: Specifies the HTTPS proxy server URL to be used for HTTPS requests.
- `no_proxy_env`: A comma-separated list of domain names or IP addresses that should bypass the proxy.
- `VLM_MODEL_NAME`: The name or path of the model to be used, e.g., `microsoft/Phi-3.5-vision-instruct`.
- `VLM_COMPRESSION_WEIGHT_FORMAT`: Specifies the format for compression weights, e.g., `int4`.
- `VLM_DEVICE`: Specifies the device to be used for computation, e.g., `CPU`.
- `VLM_SERVICE_PORT`: The port number on which the FastAPI server will run, e.g., `9764`.
- `TAG`[Optional]: Specifies the tag for the Docker image, e.g., `latest`.
- `REGISTRY`[Optional]: Specifies the Docker registry URL.
- `VLM_SEED` [Optional]: An optional environment variable used to set the seed value for deterministic behavior in the VLM inference microservice. This can be useful for debugging or reproducing results. If not provided, a random seed will be used by default.

## Supported Models

| Model Name                          | Single Image Support | Multi-Image Support | Video Support | Hardware Support                |
|-------------------------------------|----------------------|---------------------|---------------|---------------------------------|
| Qwen/Qwen2-VL-2B-Instruct           | Yes                  | Yes                 | Yes           | CPU                             |
| OpenGVLab/InternVL2-4B              | Yes                  | No                  | No            | CPU                             |
| openbmb/MiniCPM-V-2_6               | Yes                  | No                  | No            | CPU                             |
| microsoft/Phi-3.5-vision-instruct   | Yes                  | Yes                 | No            | CPU, GPU(both single frame and multi-frame)                        |
| Qwen/Qwen2.5-VL-7B-Instruct         | Yes                  | Yes                 | Yes           | CPU, GPU(single frame only)                        |

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
