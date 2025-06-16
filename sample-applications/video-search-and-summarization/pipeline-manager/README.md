# Pipeline Manager Service

## Overview
The Pipeline Manager Service is a core component of the Intel EGAI Video Summary application. It manages the video processing pipeline, coordinating various services to generate video summaries.

## Features
- Manages video processing pipeline
- Coordinates with other services like EVAM, OVMS, VLM, RabbitMQ, and Minio
    - Call minio service to save the Videos.
    - Call EVAM service to Ingest Videos
    - Read the status from the RabbitMQ Queue
    - Sends frames to VLM Service for Frame Captioning
    - Send Chunks to LLM Service for Chunk Captioning
    - Send Chunk Captions to LLM Service for Video Summarization.
- Handles video uploads and state management

## Prerequisites
- Docker
- Docker Compose

## Setup
1. Clone the repository:
   ```sh
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   cd edge-ai-libraries/sample-applications/video-search-and-summarization/pipeline-manager
   ```
2. Build the Docker image:
   ```sh
   docker build -f 'Dockerfile' -t 'pipeline-manager' .
   ```
3. To use the service refer to the docker compose (file)(/sample-applications/video-search-and-summarization/compose.yaml) and [README](/sample-applications/video-search-and-summarization/README.md)

## Environment Variables
- `no_proxy`: No proxy settings
- `http_proxy`: HTTP proxy settings
- `https_proxy`: HTTPS proxy settings
- `MINIO_ROOT_USER`: Minio root user
- `MINIO_ROOT_PASSWORD`: Minio root password
- `EVAM_HOST`: EVAM service host
- `EVAM_PIPELINE_PORT`: EVAM pipeline port
- `EVAM_PUBLISH_PORT`: EVAM publish port
- `EVAM_DEVICE`: EVAM device
- `RABBITMQ_HOST`: RabbitMQ host
- `RABBITMQ_AMQP_PORT`: RabbitMQ AMQP port
- `VLM_CAPTIONING_DEVICE`: VLM captioning device

## Usage
- Upload videos through the UI
- Monitor the processing state
- Manage the Video Summary process 
- Updates the Endpoint with state and data.

## Contributing
Contributions are welcome! Please read the [contributing guidelines](../../../../CONTRIBUTING.md) first.

## License
This project is licensed under the Apache License 2.0. See the [LICENSE](../../../../LICENSE) file for details.