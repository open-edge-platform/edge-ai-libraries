# How to publish metadata and frame over MQTT

Pre-requisites:
- `MQTT_HOST` and `MQTT_PORT` environment variable must be set for DL Streamer Pipeline Server prior to sending this curl request.
You can do this by adding these variables to `.env` file present in the same folder as `docker-compose.yml`. 
    ```sh
    MQTT_HOST=<MQTT_BROKER_IP>
    MQTT_PORT=<MQTT_BROKER_PORT>
    ```
    Alternatively, you can add them to the `environments` for DL Streamer Pipeline Server section in `docker-compose.yml`. 

    ```yaml
    dlstreamer-pipeline-server:
        environment:
          - MQTT_HOST=<MQTT_BROKER_IP>
          - MQTT_PORT=<MQTT_BROKER_PORT>
    ```

A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_mqtt_publisher/config.json`. We need to volume mount the sample config file in `docker-compose.yml` file. Refer below snippets:

```sh
    volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_mqtt_publisher/config.json to config file that DL Streamer Pipeline Server container loads.
      - "../configs/sample_mqtt_publisher/config.json:/home/pipeline-server/config.json"
```

The below CURL command publishes metadata to a MQTT broker and sends frames over RTSP for streaming.

Assuming broker is running in the same host over port `1883`, replace the `<SYSTEM_IP_ADDRESS>` field with your system IP address.  
RTSP Stream will be accessible at `rtsp://<SYSTEM_IP_ADDRESS>:8554/pallet_defect_detection`.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
                "source": {
                    "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
                    "type": "uri"
                },
                "destination": {
                    "metadata": {
                        "type": "mqtt",
                        "publish_frame":true,
                        "topic": "pallet_defect_detection"
                    },
                    "frame": {
                        "type": "rtsp",
                        "path": "pallet_defect_detection"
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

Output can be viewed on MQTT subscriber as shown below.

```sh
docker run -it --entrypoint mosquitto_sub eclipse-mosquitto:latest --topic pallet_defect_detection -p 1883 -h <SYSTEM_IP_ADDRESS>
```

For more details on MQTT you can refer this [document](./advanced-guide/detailed_usage/publisher/eis_mqtt_publish_doc.md)