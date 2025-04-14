# How to Build from Source

This guide provides step-by-step instructions for building the Chat Question-and-Answer Core Sample Application from source.

If you want to build the microservices image locally, you can optionally refer to the steps in the [Building the Backend Image](#building-the-backend-image) and [Building the UI Image](#building-the-ui-image) sections. These sections provide detailed instructions on how to build the Docker images for both the backend and UI components of the `Chat Question-and-Answer Core` application separately.

If you want to build the images via `docker compose`, please refer to the section [Build the Images via Docker Compose](#build-the-images-via-docker-compose).

Once all the images are built, go back to `chat-question-and-answer-core` directory by using `cd ..` command. Then, you can proceed to start the service using the `docker compose` command as described in the [Get Started](./get-started.md) page.

## Building the Backend Image
To build the Docker image for the `Chat Question-and-Answer Core` application, follow these steps:

1. Ensure you are in the project directory:

   ```bash
   cd sample-applications/chat-question-and-answer-core
   ```

2. Build the Docker image using the provided `Dockerfile`:

   ```bash
   docker build -t chatqna:latest -f docker/Dockerfile .
   ```

3. Verify that the Docker image has been built successfully:

   ```bash
   docker images | grep chatqna

   # You should see an entry for `chatqna` with the `latest` tag.
   ```

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

   # You should see an entry for `chatqna-ui` with the `latest` tag.
   ```

## Build the Images via Docker Compose
If you want to build the images using the `compose.yaml` file via the `docker compose` command, follow these steps:

1. Ensure you are in the project directory:

   ```bash
   cd sample-applications/chat-question-and-answer-core
   ```
2. Set Up Environment Variables:
   ```bash
      export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
      source scripts/setup_env.sh
   ```

3. Build the Docker images using the `compose.yaml` file:

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

1. Start the Docker containers with the previously built images:
   ```bash
   docker compose -f docker/compose.yaml up
   ```

2. Access the application:
   - Open your web browser and navigate to `http://<host-ip>:5173` to view the application dashboard.

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
