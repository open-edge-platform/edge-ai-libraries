# How to Build from Source [Document yet to be updated]

This section shows how to build the Video Search and Summary sample application from source.

## Prerequisites
1. Follow the instructions given in the [Get Started](./get-started.md) section.

2. Address all [prerequisites](./get-started.md#-prerequisites).

3. Configure the required [environment variables](./get-started.md#️-setting-required-environment-variables). 

## Steps to Build from Source

1. **Clone the Repository**:
    - Clone the Video Summary Sample Application repository:
      ```bash
      git clone https://github.com/open-edge-platform/edge-ai-libraries.git
      ```

2. **Navigate to the Directory**:
    - Go to the directory where the Dockerfile is located:
      ```bash
      cd edge-ai-libraries/sample-applications/video-search-and-summarization
      ```

3. **Build the Docker Image**:

    If you need to customize the application or build your own images, you can use the `build.sh` script included in the repository.

    ### ⚙️ Customizing Build Configuration

    Before running the build script, you can modify these variables in the script to control where images are pushed:

    ```bash
    # Open build.sh and update these values
    export REGISTRY_URL=<your-container-registry>  # e.g. "docker.io/username/"
    export PROJECT_NAME=<your-project-name>        # e.g. "video-summary"
    export TAG=<your-version-tag>                  # e.g. "latest" or "rc4"
    ```

    ### 🔨 Building Images

    The build script provides several options:

    ```bash
    sudo chmod +x ./build.sh
    # Build all microservice dependencies (vlm-openvino-serving, multimodal-embedding-serving, vdms-dataprep etc.)
    ./build.sh

    # Build only the sample applications (pipeline-manager, video-search and UI)
    ./build.sh --sample-app

    # Push all built images to the configured registry
    ./build.sh --push
    ```

    After building, you can verify the created images with:

    ```bash
    docker images | grep <your-project-name>
    ```


4. **Run the Docker Container**:


    The Video Search and Summary application offers multiple stacks and deployment options, to verify the newly created images run the below command to run the application:

    ```bash
    source setup.sh --summary
    ```

5. 🌐 Accessing the Application

    After successfully starting the application, you can access the UI at URL provided by following command:

    ```bash
    echo "http://${HOST_IP}:${APP_HOST_PORT}"
    ```

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