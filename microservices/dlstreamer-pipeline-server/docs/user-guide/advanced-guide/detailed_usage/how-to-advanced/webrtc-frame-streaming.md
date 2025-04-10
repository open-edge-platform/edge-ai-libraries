# WebRTC frame streaming

EVAM supports streaming the frames on WebRTC protocol using mediamtx media server.
There is a dedicated docker compose file for demonstrating WebRTC streaming for EVAM. It is available in EVAM's github repository, under the "docker" folder i.e., `[EVAM_WORKDIR]/docker/docker-compose-mediamtx.yml`
Below are the necessary configuration to be aware of (or modify accordingly based on your deployment) in `[EVAM_WORKDIR]/docker/.env` (They will be consumed appropriately in `[EVAM_WORKDIR]/docker/docker-compose-mediamtx.yml`):
```sh
WHIP_SERVER_IP=<HOST_IP> # It should be the IP address of the machine on which open mediamtx container is running.
WHIP_SERVER_PORT=8889 # It is the port which is configured for mediamtx server. Default port is 8889.
```
After setting all the above information, we can start the WebRTC streaming:
- Start the services
    ```sh
        docker compose -f docker-compose-mediamtx.yml up
    ```
- Open another terminal and start a pipeline in EVAM with the below curl command.
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
                "type": "webrtc",
                "peer-id": "pallet-defect-detection"
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
- Open `http://<HOST_IP>:8889/<peer-id>` in your browser to view the WebRTC stream:
    ![Stream output on browser using WebRTC](../../../images/sample_webrtc_mediamtx.png)