# How to use GPU for decode and inference

In order to benefit from hardware acceleration devices, pipelines can be constructed in a
manner that different stages such as decoding, inference etc., can make use of them.

## Pre-requisites

### Ensure you have a GPU

To determine which graphics processor you have, please follow [this](https://dgpu-docs.intel.com/devices/hardware-table.html) document.

### Provide GPU access to the container

For containerized application such as the Deep Learning Streamer Pipeline Server (DL Streamer
Pipeline server), first we need to provide GPU device(s) access to the container user. This
can be done by making the following changes to the docker compose file.

```yaml
services:
  dlstreamer-pipeline-server:
    group_add:
      # render group ID for ubuntu 22.04 host OS
      - "110"
      # render group ID for ubuntu 24.04 host OS
      - "992"
    devices:
      # you can add specific devices in case you don't want to provide access to all like below.
      - "/dev:/dev"
```
The changes above adds the container user to the `render` group and provides access to the GPU devices.

### Hardware specific encoder/decoders
Unlike the changes done for the container above, the following requires a modification to the media pipeline itself.

Gstreamer has a variety of hardware specific encoders and decoders elements such as Intel specific VA-API elements that you can benefit from by adding them into your media pipeline. Examples of such elements are `vah264dec`, `vah264enc`, `vajpegdec`, `vajpegdec`, etc.

Additionally, one can also enforce zero-copy of buffers using GStreamer caps (capabilities) to the pipeline by adding `video/x-raw(memory: VAMemory)` for Intel GPUs (integrated and discrete).

Read the DL Streamer [docs](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/gpu_device_selection.md) for more information on GPU selection.

### GPU specific element properties
DL Streamer inference elements also provides property such as `pre-process-backend=va-surface-sharing` and `device=GPU` to pre-process and infer on GPU. Read the DL Streamer [docs](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/model_preparation.md#2-model-pre--and-post-processing) for more details.

## Tutorial on how to use GPU specific pipelines

> Note - DL Streamer Pipeline Server already provides a default `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` file that includes the necessary GPU access to the container.

- A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_gpu_decode_and_inference/config.json`. We need to volume mount the sample config file into dlstreamer-pipeline-server service present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` file. Refer below snippets:

    ```sh
        volumes:
        # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_gpu_decode_and_inference/config.json to config file that DL Streamer Pipeline Server container loads.
        - "../configs/sample_gpu_decode_and_inference/config.json:/home/pipeline-server/config.json"
    ```

- Restart DL Streamer pipeline server

    ```sh
        cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/
        docker compose down
        docker compose up
    ```

- In the pipeline string in the above config file, we have added GPU specific elements/properties for decoding and inferencing on GPU backend. We will now start the pipeline with a curl request

    ```sh
    curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
        "source": {
            "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
            "type": "uri"
        },
        "destination": {
            "metadata": {
                "type": "file",
                "path": "/tmp/results.jsonl",
                "format": "json-lines"
            }
        },
        "parameters": {
            "detection-properties": {
                "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml"
            }
        }
    }'
    ```
- We should see the metadata results in `/tmp/results.jsonl` file.

- To perform decode and inference on CPU, please see [this document](./how-to-use-cpu-for-decode-and-inference.md). For more combinations of different devices for decode and inference, please see [this document](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/performance_guide.md).
