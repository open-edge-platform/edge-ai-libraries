# Build from Source

You can build either an optimized or an extended DL Streamer Pipeline Server image (for both
Ubuntu22 and Ubuntu24) based on your use case. The extended image contains the Geti SDK, the
OpenVINO Model API and ROS2 on top of the optimized image.

> **Note:** Ensure to set the right values in the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env`
> file for building DL Streamer Pipeline Server optimized image and DL Streamer Pipeline Server
> extended image when you follow the below steps. The mentioned file has the necessary details
> written as comments.

## Steps

### Prerequisites

1. Clone the Edge-AI-Libraries repository from open edge platform and change to the docker directory inside DL Streamer Pipeline Server project.

    ```sh
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git
    cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/
    ```

2. Add the following lines in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` if you are behind a proxy.

    ``` sh
    http_proxy= # example: http_proxy=http://proxy.example.com:891
    https_proxy= # example: https_proxy=http://proxy.example.com:891
    no_proxy= # example: no_proxy=localhost,127.0.0.1
    ```

3. Update the following lines in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` for choosing the right base and target images and
also for naming the image that gets built.

    ``` sh
    # See .env file for example values
    BASE_IMAGE=

    # See .env file for example values
    DLSTREAMER_PIPELINE_SERVER_IMAGE=

    # See .env file for example values
    BUILD_TARGET=
    ```

> **Note:** If you do not have access to the above mentioned `BASE_IMAGE`, then you can build
> [DL Streamer docker image from source](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/dev_guide/advanced_install/advanced_build_docker_image.html)
> and use it as `BASE_IMAGE` in the above mentioned `.env` file.

### Build DL Streamer Pipeline Server image and start container

1. Run the following commands in the project directory

    ```sh
    cd docker
    source .env # sometimes this is needed as docker compose doesn't always pick up the necessary env variables
    docker compose build
    ```

    The docker image of DL Streamer Pipeline Server is now built (based on the .env changes done above) and available for you to run.

2. Run the below command to start the container

    ```sh
    docker compose up
    ```

### Run default sample

Refer [here](../get-started.md#run-default-sample) to run default sample upon bringing up DL Streamer Pipeline Server container.

## Learn More

- Understand the components, services, architecture, and data flow, in the [Overview](../index.md)
- For more details on advanced configuration, usage of features refer to [Detailed Usage](../advanced-guide.md)
- For more tutorials please refer to the `How-to` section
