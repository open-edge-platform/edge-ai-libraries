# How to use CPU for decode and inference

## Tutorial on how to use CPU specific pipelines

- A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_cpu_decode_and_inference/config.json`. We need to volume mount the sample config file into dlstreamer-pipeline-server service present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` file. Refer below snippets:

    ```sh
        volumes:
        # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_cpu_decode_and_inference/config.json to config file that DL Streamer Pipeline Server container loads.
        - "../configs/sample_cpu_decode_and_inference/config.json:/home/pipeline-server/config.json"
    ```
- Restart DL Streamer pipeline server

    ```sh
        cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/
        docker compose down
        docker compose up
    ```

- In the pipeline string in the above config file, we have added CPU specific elements/properties for decoding and inferencing on CPU backend. We will now start the pipeline with a curl request

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

- To perform decode and inference on GPU, please see [this document](./how-to-use-gpu-for-decode-and-inference.md). For more combinations of different devices for decode and inference, please see [this document](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/performance_guide.md).
