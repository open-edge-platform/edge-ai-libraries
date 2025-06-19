```{eval-rst}
:orphan:
```
# Generic Plugin

Generic Plugin is a gstreamer generic source plugin that communicates and streams from a GenICam based camera which provides a GenTL producer. In order to use
the generic plugin with DL Streamer Pipeline Server one must install the respective GenICam camera SDK and make sure the compatible GenTL producer for the camera is installed.

>**Refer [src-gst-gencamsrc/README.md](../src-gst-gencamsrc/README.md) for more information on Generic Plugin**
 ----

**For working with Genicam USB3 Vision camera please install the respective camera SDK by referring the below section**

## Adding new GigE camera support to DL Streamer Pipeline Server

In order to use the generic plugin with newer Genicam camera SDK follow the below steps:

1. Install the respective GenICam camera SDK by adding the camera SDK installation steps in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/Dockerfile`. The camera SDK will be installed during docker build and one can install multiple camera SDKs in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/Dockerfile`. Refer Dockerfile reference documentation (<https://docs.docker.com/engine/reference/builder/>) for Dockerfile Instructions. Typically one would need to use `RUN <command>` instruction to execute shell commands for installing newer camera sdk. In case the camera SDK cannot be downloaded in a non-interactive manner then one would need to place the camera SDK under `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server` directory, use the `COPY` instruction in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/Dockerfile` to use the camera SDK in the build context and then use the `RUN` instruction for installing the camera SDK during docker build.

2. After making sure the compatible GenTL producer is successfully installed one must add a case statement in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/thirdparty/gentl_producer_env.sh` script to export the GenTL producer path to `GENICAM_GENTL64_PATH` env variable. In order to verify the GenTL producer path one can search for the `.cti` file under the installation path. Typically GenTL provider is characterized by a file with `.cti` extension. Path to cti library containing folder must be exported to env variable named `GENICAM_GENTL64_PATH` (`GENICAM_GENTL32_PATH` for 32 bit providers).

3. Set `GENICAM` env variable in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` to execute the corresponding case statement in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/thirdparty/gentl_producer_env.sh` and export the GenTL producer path accordingly. GenTL producer path will be exported during docker runtime. Hence one can choose to add install multiple Genicam camera SDK during docker build and then switch between GenTL providers during docker runtime by modifying the `GENICAM` env variable in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml`.

**Refer the below snippet example to select `Basler` camera and export its GenTL producer path in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` assuming the corresponding Basler Camera SDK and GenTL producer is installed.**

```bash
 dlstreamer-pipeline-server:
 ...
   environment:
   ...
   # Setting GENICAM value to the respective camera which needs to be used
   GENICAM: "Balluff"
```

**Note:** - Please make sure to do `docker compose down` and `docker compose down -d` after making changes in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml`
