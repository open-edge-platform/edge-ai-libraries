# Use GPU or NPU for Decoding and Inference

In order to benefit from hardware acceleration devices, pipelines can be constructed in a
manner that different stages such as decoding, inference etc., can make use of them.

## Pre-requisites

### Ensure you have a GPU or NPU

To determine which graphics processor you have, refer to the [Hardware table](https://dgpu-docs.intel.com/devices/hardware-table.html) document.

### Provide GPU or NPU access to the container

For containerized applications such as the Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server), you must first grant the container user access to GPU/NPU device(s).

Because Docker Compose does not evaluate shell expressions, you need to determine the `render` group ID on the host system and define/export it as an environment variable **before** running Docker Compose. You can add group ID in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` or export it using below command:

    ```sh
        export RENDER_GID=$(stat -c "%g" /dev/dri/render* | head -1)
    ```

### Hardware specific encoder/decoders
Unlike the changes done for the container above, the following requires a modification to the media pipeline itself.

Gstreamer has a variety of hardware specific encoders and decoders elements such as Intel specific VA-API elements that you can benefit from by adding them into your media pipeline. Examples of such elements are `vah264dec`, `vah264enc`, `vajpegdec`, `vajpegdec`, etc.

Additionally, one can also enforce zero-copy of buffers using GStreamer caps (capabilities) to the pipeline by adding `video/x-raw(memory: VAMemory)` for Intel GPUs (integrated and discrete) or NPU devices.

Read the DL Streamer [docs](https://github.com/open-edge-platform/dlstreamer/blob/main/docs/source/dev_guide/gpu_device_selection.md) for more information on GPU selection.

### GPU/NPU specific element properties
DL Streamer inference elements also provides property such as `pre-process-backend=va-surface-sharing` or `pre-process-backend=va`and `device=GPU` or `device=NPU` to pre-process and infer on GPU/NPU. Read the DL Streamer [docs](https://github.com/open-edge-platform/dlstreamer/blob/main/docs/source/dev_guide/model_preparation.md#2-model-pre--and-post-processing) for more details.

## Tutorial on how to use GPU/NPU specific pipelines

> **Note:** - DL Streamer Pipeline Server already provides a default `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml`
> file that includes the necessary GPU/NPU access to the container.

- A sample config for GPU has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_gpu_decode_and_inference/config.json`. 
- A sample config for NPU has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_npu_decode_and_inference/config.json`.

We need to volume mount the sample config file into dlstreamer-pipeline-server service present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` file. Refer below snippets:

- GPU:
    ```sh
        volumes:
        # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_gpu_decode_and_inference/config.json to config file that DL Streamer Pipeline Server container loads.
        - "../configs/sample_gpu_decode_and_inference/config.json:/home/pipeline-server/config.json"
    ```

- NPU:

    ```sh
        volumes:
        # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_npu_decode_and_inference/config.json to config file that DL Streamer Pipeline Server container loads.
        - "../configs/sample_npu_decode_and_inference/config.json:/home/pipeline-server/config.json"
    ```

- Restart DL Streamer pipeline server

    ```sh
        cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/
        docker compose down
        docker compose up
    ```

- In the pipeline string in the above config files, we have added GPU/NPU specific elements/properties for decoding and inferencing on GPU/NPU backend. We will now start the pipeline with a curl request

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

- To perform decode and inference on CPU, see [this document](./use-cpu-for-decode-and-inference.md). For more combinations of different devices for decode and inference, see the [Performance Guide](https://github.com/open-edge-platform/dlstreamer/blob/main/docs/source/dev_guide/performance_guide.md).
