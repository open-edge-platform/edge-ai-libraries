# How to build from source

You can build either an optimized or an extended DL Streamer Pipeline Server image (for both Ubuntu22 and Ubuntu24) based on your use case. The extended image contains the Geti SDK, the OpenVINO Model API and ROS2 on top of the optimized image.

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

3. Update the following lines in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` for choosing the right base image and also for naming the image that gets built.

    ``` sh
    # See .env file for example values
    BASE_IMAGE=

    # See .env file for example values
    DLSTREAMER_PIPELINE_SERVER_IMAGE=

    # See .env file for example values
    BUILD_TARGET=
    ```

    Note: If you do not have access to the above mentioned `BASE_IMAGE`, then you can build [DL Streamer docker image from source](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/dl-streamer#build-the-dlstreamer-docker-image-with) and use it as `BASE_IMAGE` in the above mentioned `.env` file

### Build DL Streamer Pipeline Server image and start container

1. Run the following commands in the project directory

    ```sh
    cd docker
    source .env # sometimes this is needed as docker compose doesn't always pick up the necessary env variables
    docker compose build
    ```
---

2. Once the build is complete, list the docker images
    ```sh
    docker image ls
    ```
Based on the `.env` file changes done above, verify that the appropriate image from the following is present in the system after the build is successful
- `intel/dlstreamer-pipeline-server:<latest-version-number>-ubuntu22`
- `intel/dlstreamer-pipeline-server:<latest-version-number>-ubuntu24`
- `intel/dlstreamer-pipeline-server:<latest-version-number>-extended-ubuntu22`
- `intel/dlstreamer-pipeline-server:<latest-version-number>-extended-ubuntu24`

---

3. Run the below command to start the container 
    ```sh
    docker compose up
    ```
---
### Run default sample
Refer [here](./get-started.md#run-default-sample) to run default sample upon bringing up DL Streamer Pipeline Server container.

## Learn More

-   Understand the components, services, architecture, and data flow, in the [Overview](./Overview.md)
-   For more details on advanced configuration, usage of features refer to [Detailed Usage](./advanced-guide/Overview.md)
-   For more tutorials please refer `How-to` section