# How to use GPU for inference

## Steps

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
            "device": "GPU"
        }
    }
}'
```
Save the config.json and restart DL Streamer pipeline server
Ensure that the changes made to the config.json are reflected in the container by volume mounting (as mentioned in this [document](./how-to-change-dlstreamer-pipeline.md)) it.

```sh
    cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/
    docker compose down
    docker compose up
```
We should see the metadata results in `/tmp/results.jsonl` file like in previous tutorial.