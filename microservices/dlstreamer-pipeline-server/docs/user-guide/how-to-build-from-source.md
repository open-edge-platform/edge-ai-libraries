# How to build from source

## Steps

### Prerequisites
Add the following lines in `[EVAM_WORKDIR]/docker/.env` if you are behind a proxy.

  ``` sh
  http_proxy= # example: http_proxy=http://proxy.example.com:891
  https_proxy= # example: https_proxy=http://proxy.example.com:891
  no_proxy= # example: no_proxy=localhost,127.0.0.1
  ```

### Build EVAM image and start container

1. Run the following commands in `[EVAM_WORKDIR]`:

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
Verify that following image `intel/edge-video-analytics-microservice:<latest-version-number>` is present in the system after the build is successful

---

3. Run the below command to start the container 
```sh
docker compose up
```
---
### Run default sample
Refer [here](./get-started.md#run-default-sample) to run default sample upon bringing up EVAM container.

## Learn More

-   Understand the components, services, architecture, and data flow, in the [Overview](./Overview.md)
-   For more details on advanced configuration, usage of features refer to [Detailed Usage](./advanced-guide/Overview.md). 
-   For more tutorials please refer `How-to` section