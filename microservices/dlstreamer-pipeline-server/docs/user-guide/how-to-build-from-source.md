# How to build from source

## Steps

### Prerequisites
Add the following lines in `[WORKDIR]/docker/.env` if you are behind a proxy.

  ``` sh
  http_proxy= # example: http_proxy=http://proxy.example.com:891
  https_proxy= # example: https_proxy=http://proxy.example.com:891
  no_proxy= # example: no_proxy=localhost,127.0.0.1
  ```

### Build DL Streamer Pipeline Server image and start container

1. Clone the repository and change to the project directory for DL Streamer Pipeline Server

```sh
git clone <link-to-repository>
cd <path/to/dlstreamer-pipeline-server/>
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
Verify that following image `intel/dlstreamer-pipeline-server:<latest-version-number>` is present in the system after the build is successful

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