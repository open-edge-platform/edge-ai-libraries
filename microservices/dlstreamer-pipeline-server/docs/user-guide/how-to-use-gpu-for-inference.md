# How to use GPU for inference

## Pre-requisites
In order to benefit from hardware acceleration, pipelines can be constructed such that different stages such as decoding, inference etc can make use of these devices.
For containerized application such as the DLStreamer Pipeline Server, first we need to provide container user to have access to the GPU devices.

### Provide GPU access to the container
This can be done by making the following changes to the docker compose file.

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

### Hardware specific encoder/decoders
Unlike the changes done for the container above, the following requires a modification to the media pipeline itself.

Gstreamer has a variety of hardware specific encoders and decoders elements such as Intel specific VA-API elements that you can benefit from by adding them
in your media pipeline. Examples of such elements are `vah264dec`, `vah264enc`, `vajpegdec`, `vajpegdec`, etc.

Additionally, one can also enforce zero-copy of buffers using Gstreamer caps (capabilities) to the pipeline by adding `video/x-raw(memory: VAMemory)` for Intel GPUs (integrated and discrete)

Read DLStreamer [docs](https://dlstreamer.github.io/dev_guide/gpu_device_selection.html) for more.

### GPU specific element properties
DLStreamer inference elements also provides property such as `device=GPU` and `pre-process-backend=va-surface-sharing` to infer and pre-process on GPU. Read DLStreamer [docs](https://dlstreamer.github.io/dev_guide/model_preparation.html#model-pre-and-post-processing) for more.

## Tutorial on how to use GPU specific pipelines

> Note - DLStreamer Pipeline Server already provides a default `docker-compose.yml` file that includes the necessary GPU access to the containers.

For inferencing with GPU backend, we will use the REST API to start a pipeline.


Replace the following sections in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/config.json` with the following

- replace `"pipeline"` section with  
    ```sh
    "pipeline": "{auto_source} name=source  ! parsebin ! vah264dec ! vapostproc ! video/x-raw(memory:VAMemory) ! gvadetect name=detection ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
    ```
In the pipeline string, we have added GPU specific elements. We will now start the pipeline with a curl request

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
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "GPU",
            "pre-process-backend":"va-surface-sharing"
        }
    }
}'
```
> Note DLStreamer Pipeline Server also allows users to add  element properties model, device and pre-process-backend as past of REST payload for convenience. Any properties set here, will always replace any existing propery set to the element in the pipeline before actually launching it.

Save the `config.json` and restart DL Streamer pipeline server
Ensure that the changes made to the config.json are reflected in the container by volume mounting (as mentioned in this [document](./how-to-change-dlstreamer-pipeline.md)) it.

```sh
    cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/
    docker compose down
    docker compose up
```
We should see the metadata results in `/tmp/results.jsonl` file like in previous tutorial.