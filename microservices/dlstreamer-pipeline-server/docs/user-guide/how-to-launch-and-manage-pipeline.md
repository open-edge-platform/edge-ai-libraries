# How to launch and manage pipeline (via script)

Within a running DL Streamer Pipeline Server container, you can start and stop any dlstreamer pipeline on demand either via python snippet or shell script. This is useful in scenarios where we want to automate the process of running or stopping the pipeline.

## Steps

1. A sample config has been provided for this tutorial at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_mqtt_publisher/config.json`. We need to volume mount the sample config file in `docker-compose.yml` file. Refer below snippets:

```sh
    volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_mqtt_publisher/config.json to config file that DL Streamer Pipeline Server container loads.
      - "../configs/sample_mqtt_publisher/config.json:/home/pipeline-server/config.json"
```

2. Update environment variables file present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` with below mentioned variables. Please add corresponding IP address in place of `<MQTT_BROKER_IP_ADDRESS>` below -
```sh
MQTT_HOST=<MQTT_BROKER_IP_ADDRESS>
MQTT_PORT=1883
```

3. Start the DL Streamer pipeline server
```sh
cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/
docker compose up
```

4. Start the pipeline either via python snippet or shell script.

* To use python snippet, save the below snippet on your system as `start_pipeline.py`.

`NOTE` Please make sure to intall python libraries "requests" and "json" if not already installed before running the below python snippet.

```
import requests
import json
url = "http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection"
headers = {
    "Content-Type": "application/json"
}
data = {
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "publish_frame": False,
            "topic": "dlstreamer_pipeline_results"
        },
        "frame": {
            "type": "rtsp",
            "path": "dlstreamer_pipeline_results"
        }
    },
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
}
response = requests.post(url, headers=headers, data=json.dumps(data))
print("Status Code:", response.status_code)
print("Response:", response.text)
```

Run the file using following command
```sh
python3 start_pipeline.py
```

* To use shell script, save the below script as `start_pipeline.sh`.
```sh
#!/bin/bash
curl -X POST http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection \
  -H "Content-Type: application/json" \
  -d '{
        "source": {
            "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
            "type": "uri"
        },
        "destination": {
            "metadata": {
                "type": "mqtt",
                "publish_frame": false,
                "topic": "dlstreamer_pipeline_results"
            },
            "frame": {
                "type": "rtsp",
                "path": "dlstreamer_pipeline_results"
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

Execute the following shell script as follows-
```sh
chmod +x start_pipeline.sh
./start_pipeline.sh
```

`NOTE` Instance ID of the pipeline will be mentioned in the "response" field after successfully running the above snippet. This ID can be used later to stop the pipeline as mentioned in step 7.

5. Run the following command to check MQTT messages. Replace `<SYSTEM_IP_ADDRESS>` with corresponding IP address.
```sh
docker run -it --entrypoint mosquitto_sub eclipse-mosquitto:latest --topic dlstreamer_pipeline_results -p 1883 -h <SYSTEM_IP_ADDRESS>
```

6. RTSP stream can also be viewed at rtsp://<SYSTEM_IP_ADDRESS>:8554/dlstreamer_pipeline_results. Please replace `<SYSTEM_IP_ADDRESS>` with corresponding IP address.

7. Stop the pipeline either via python snippet or shell script. Replace `<instance-id>` with corresponding ID obtained from step 4 below.

* To use python snippet, save the below snippet on your system as `stop_pipeline.py`.
```
import requests
url = "http://localhost:8080/pipelines/<instance-id>"
response = requests.delete(url)
print(f"Status Code: {response.status_code}")
print(f"Response Body: {response.text}")
```

Run the file using following command
```sh
python3 stop_pipeline.py
```

* To use shell script, save the below script as `stop_pipeline.sh`.
```sh
#!/bin/bash
URL="http://localhost:8080/pipelines/<instance-id>"
curl --location -X DELETE "$URL"
```

Execute the shell script as follows-
```sh
chmod +x stop_pipeline.sh
./stop_pipeline.sh
```
