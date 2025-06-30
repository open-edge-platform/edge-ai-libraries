# Run multistream pipelines with shared model instance

## Steps

DL Streamer Pipeline Server can execute multiple input streams in parallel. If streams use the same pipeline configuration, it is recommended to create a shared inference element. The ‘model-instance-id=inst0’ parameter constructs such element. 

`model-instance-id` is an optional property that will hold the model in memory instead of releasing it when the pipeline completes. This improves load time and reduces memory usage when launching the same pipeline multiple times. The model is associated with the given ID to allow subsequent runs to use the same model instance.

1. Update the default config present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/config.json`. Replace `pipeline` parameter in default config with below `pipeline`.

```sh
"pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
```

2. Allow DL Streamer Pipeline Server to read the above modified configuration by volume mounting the modified default config in `docker-compose.yml` file. To learn more, refer [here](../../../how-to-change-dlstreamer-pipeline.md).

3. Start DL Streamer Pipeline Server container
```sh
docker compose up -d
```
`NOTE` Run the above command in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/`

4. Start the first pipeline with following curl command - 
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

Your terminal output would be as shown below - 
```sh
dlstreamer-pipeline-server  | FpsCounter(last 1.03sec): total=48.57 fps, number-streams=1, per-stream=48.57 fps
dlstreamer-pipeline-server  | FpsCounter(average 40.64sec): total=50.47 fps, number-streams=1, per-stream=50.47 fps
dlstreamer-pipeline-server  | FpsCounter(last 1.01sec): total=49.55 fps, number-streams=1, per-stream=49.55 fps
dlstreamer-pipeline-server  | FpsCounter(average 41.65sec): total=50.45 fps, number-streams=1, per-stream=50.45 fps
```

5. You can start the second instance of the same pipeline in parallel by sending the same curl command as above. You can use a different video for second instance by changing `uri` config in above curl request. Now you should be able to see `number-streams=2` in your output.

```sh
dlstreamer-pipeline-server  | FpsCounter(last 1.00sec): total=49.97 fps, number-streams=2, per-stream=24.98 fps (23.98, 25.98)
dlstreamer-pipeline-server  | FpsCounter(average 14.17sec): total=49.25 fps, number-streams=2, per-stream=24.63 fps (23.50, 25.75)
dlstreamer-pipeline-server  | FpsCounter(last 1.00sec): total=48.98 fps, number-streams=2, per-stream=24.49 fps (24.99, 23.99)
dlstreamer-pipeline-server  | FpsCounter(average 15.19sec): total=49.24 fps, number-streams=2, per-stream=24.62 fps (23.57, 25.68)
```