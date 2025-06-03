# How to build from source

## Steps

### Prerequisites
Add the following lines in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` if you are behind a proxy.

  ``` sh
  http_proxy= # example: http_proxy=http://proxy.example.com:891
  https_proxy= # example: https_proxy=http://proxy.example.com:891
  no_proxy= # example: no_proxy=localhost,127.0.0.1
  ```

Update the following lines for choosing the right base image and also for naming the image that gets built.

  ``` sh
  # For Ubuntu 22.04: intel/dlstreamer:2025.0.1.3-ubuntu22
  # For Ubuntu 24.04: intel/dlstreamer:2025.0.1.3-ubuntu24
  BASE_IMAGE=

  # For Ubuntu 22.04: intel/dlstreamer-pipeline-server:3.1.0-ubuntu22
  # For Ubuntu 24.04: intel/dlstreamer-pipeline-server:3.1.0-ubuntu24
  DLSTREAMER_PIPELINE_SERVER_IMAGE=
  ```

### Build DL Streamer Pipeline Server image and start container

1.  Clone the Edge-AI-Libraries repository from open edge platform and change to the docker directory inside DL Streamer Pipeline Server project.

```sh
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/
```
---

2. Run the following commands in the project directory

```sh
cd docker
source .env # sometimes this is needed as docker compose doesn't always pick up the necessary env variables
docker compose build
```
---

3. Once the build is complete, list the docker images
```sh
docker image ls
```
Verify the following image `intel/dlstreamer-pipeline-server:<latest-version-number>-ubuntu22` or `intel/dlstreamer-pipeline-server:<latest-version-number>-ubuntu24` is present in the system after the build is successful

---

4. Run the below command to start the container 
```sh
docker compose up
```
---
### Run default sample
Refer [here](./get-started.md#run-default-sample) to run default sample upon bringing up DL Streamer Pipeline Server container.

## Learn More

-   Understand the components, services, architecture, and data flow, in the [Overview](./Overview.md)
-   For more details on advanced configuration, usage of features refer to [Detailed Usage](./advanced-guide/Overview.md). 
-   For more tutorials please refer `How-to` section