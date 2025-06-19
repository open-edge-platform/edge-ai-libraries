# Enable Open Telemetry

DL Streamer Pipeline Server supports gathering metrics over Open Telemetry. The supported metrics currently are:
- `cpu_usage_percentage`: Tracks CPU usage percentage of DL Streamer Pipeline Server python process
- `memory_usage_bytes`: Tracks memory usage in bytes of DL Streamer Pipeline Server python process
- `fps_per_pipeline`: Tracks FPS for each active pipeline instance in DL Streamer Pipeline Server
There is a dedicated docker compose file for demonstrating Open Telemetry for DL Streamer Pipeline Server. It is available in DL Streamer Pipeline Server's github repository, under the "docker" folder i.e., `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose-otel.yml`
The way it works is, DL Streamer Pipeline Server exports the telemetry data to the open telemetry service (otel/opentelemetry-collector-contrib) and then prometheus service scrapes the data which can be visualized. The necessary configuration for open telemetry and prometheus services is located at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/open_telemetry/otel-collector-config.yaml` and `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/open_telemetry/prometheus.yml` respectively.
Below are the necessary configuration to be aware of (or modify accordingly based on your deployment) in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` (They will be consumed appropriately in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose-otel.yml`):
```sh
ENABLE_OPEN_TELEMETRY=true # true to enable open telemetry and false otherwise
OTEL_COLLECTOR_HOST=otel-collector # open telemetry container name in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose-otel.yml`. Can also be the IP address of the machine if open telemetry container is running on a different machine. Ex: OTEL_COLLECTOR_HOST=10.10.10.10
OTEL_COLLECTOR_PORT=4318 # Open telemetry container will receive data on this port. If this value is changed, ensure to update `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/open_telemetry/otel-collector-config.yaml` appropriately.
OTEL_EXPORT_INTERVAL_MILLIS=5000 # How often to export metrics to the open telemetry collector in milli seconds.
```
With this information at hand, let us now see open telemetry in action.
- Start the services
    ```sh
        docker compose -f docker-compose-otel.yml up
    ```
- Open another terminal and start a pipeline in DL Streamer Pipeline Server with the below curl command.
    ```sh
        curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
        "source": {
            "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
            "type": "uri"
        },
        "destination": {
            "metadata": {
                "type": "file",
                "path": "/tmp/results.jsonl",
                "format": "json-lines"
            },
            "frame": {
                "type": "rtsp",
                "path": "pallet-defect-detection"
            }
        },
        "parameters": {
            "detection-properties": {
                "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
                "device": "CPU"
            }
        }
    }'
    ```
    Note down the `pipeline_id` returned by this command. Ex: "`658a5260f37d11ef94fc0242ac160005`"
- Open `http://<HOST_IP>:<PROMETHEUS_PORT>` in your browser to view the prometheus console and try out the below queries (`PROMETHEUS_PORT` is by default configured as 9999 in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` file):
    - `cpu_usage_percentage`
    - `memory_usage_bytes`
    - `fps_per_pipeline{}`
        - If you are starting multiple pipelines, then it can also be queried per pipeline ID. Example: `fps_per_pipeline{pipeline_id="658a5260f37d11ef94fc0242ac160005"}`
    ![Open telemetry fps_per_pipeline example in prometheus](../../../images/prometheus_fps_per_pipeline.png)