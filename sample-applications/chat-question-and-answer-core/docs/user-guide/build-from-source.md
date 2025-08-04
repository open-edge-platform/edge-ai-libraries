# How to Build from Source

This guide provides step-by-step instructions for building the Chat Question-and-Answer Core Sample Application from source.

If you want to build the microservices image locally, you can optionally refer to the steps in the [Building the Backend Image](#building-the-backend-image) and [Building the UI Image](#building-the-ui-image) sections. These sections provide detailed instructions on how to build the Docker images for both the backend and UI components of the `Chat Question-and-Answer Core` application separately.

If you want to build the images via `docker compose`, please refer to the section [Build the Images via Docker Compose](#build-the-images-via-docker-compose).

Once all the images are built, go back to `chat-question-and-answer-core` directory by using `cd ..` command. Then, you can proceed to start the service using the `docker compose` command as described in the [Get Started](./get-started.md) page.

> **Note:** 
> - The build instruction is applicable only on an Ubuntu system. Build from source is not supported for the sample application on [Edge Microvisor Toolkit (EMT)](https://github.com/open-edge-platform/edge-microvisor-toolkit). The user is recommended to use prebuilt images on EMT. 

## Building the Backend Image
To build the Docker image for the `Chat Question-and-Answer Core` application, follow these steps:

1. Ensure you are in the project directory:

   ```bash
   cd sample-applications/chat-question-and-answer-core
   ```

2. Build the Docker image using the provided `Dockerfile` based on your setup.

   Choose one of the following options:

   - CPU-only inferencing (default configuration):

     ```bash
     docker build -t chatqna:latest -f docker/Dockerfile .
     ```

     This build the image to support CPU-based inferencing, suitable for hardware setups without GPU support.

   - GPU-enabled inferencing (also support CPU):

     ```bash
     docker build -t chatqna:latest --build-arg USE_GPU=true --build-arg GPU_TYPE=dgpu -f docker/Dockerfile .
     ```

     This build the image with additional GPU support for accelerated inferencing. It still works on CPU-only systems, offering flexibility across different hardware setups.

3. Verify that the Docker image has been built successfully:

   ```bash
   docker images | grep chatqna
   ```

   You should see an entry for `chatqna` with the `latest` tag.

## Building the UI image
To build the Docker image for the `chatqna-ui` application, follow these steps:

1. Ensure you are in the `ui/` project directory:

   ```bash
   cd sample-applications/chat-question-and-answer-core/ui
   ```

2. Build the Docker image using the provided `Dockerfile`:

   ```bash
   docker build -t chatqna-ui:latest .
   ```

3. Verify that the Docker image has been built successfully:

   ```bash
   docker images | grep chatqna-ui
   ```

   You should see an entry for `chatqna-ui` with the `latest` tag.

## Build the Images via Docker Compose
This guide explains how to build the images using the `compose.yaml` file via the `docker compose` command. It also outlines how to enable GPU support during the build process.

1. Ensure you are in the project directory:

   ```bash
   cd sample-applications/chat-question-and-answer-core
   ```

2. Set Up Environment Variables:

   Choose one of the following options depends on your hardware setups:

   - For CPU-only setup (default):

     ```bash
     export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
     source scripts/setup_env.sh
     ```

   - For GPU-enabled setup:

     ```bash
     export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
     source scripts/setup_env.sh -d gpu
     ```

   ℹ️ The `-d gpu` flag enables the GPU-DEVICE profile required for GPU-based execution.

3. Build the Docker images defined in the `compose.yaml` file:

   ```bash
   docker compose -f docker/compose.yaml build
   ```

4. Verify that the Docker images have been built successfully:
   ```bash
   docker images | grep chatqna
   ```

   You should see entries for both `chatqna` and `chatqna-ui`.

## Running the Application Container
After building the images for the `Chat Question-and-Answer Core` application, you can run the application container using `docker compose` by following these steps:

1. **Set Up Environment Variables**:

   Choose one of the following options depends on your hardware setups:

   - For CPU-only setup (default):

     ```bash
     export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
     source scripts/setup_env.sh
     ```

   - For GPU-enabled setup:

     ```bash
     export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
     source scripts/setup_env.sh -d gpu
     ```

   Configure the models to be used (LLM, Embeddings, Rerankers) through a YAML configuration file, as outlined in the [Get-Started: Running The Application using Docker Compose](./get-started.md#running-the-application-using-docker-compose) section.

   Refer to and use the same list of models as documented in [Chat Question-and-Answer](../../../chat-question-and-answer/docs/user-guide/get-started.md#supported-models).


2. Start the Docker containers with the previously built images:

   ```bash
   docker compose -f docker/compose.yaml up
   ```

3. Access the application:

   - Open your web browser and navigate to `http://<host-ip>:8102` to view the application dashboard.

## Verification

- Ensure that the application is running by checking the Docker container status:

  ```bash
  docker ps
  ```

- Access the application dashboard and verify that it is functioning as expected.

## Troubleshooting

- If you encounter any issues during the build or run process, check the Docker logs for errors:

  ```bash
  docker logs <container-id>
  ```