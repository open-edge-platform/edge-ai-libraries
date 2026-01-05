# How to download and run YOLO models

## Steps

This tutorial shows how to download YOLO models (YOLOv8, YOLOv9, YOLOv10, YOLO11) and run as part of object detection pipeline.

For downloading all supported YOLO models and converting them to OpenVINO IR format, please refer to this [document](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/yolo_models.md).

### Download
#### Step 1: Create virtual environment
```sh
python -m venv ov_env
```

#### Step 2: Activate virtual environment
```sh
source ov_env/bin/activate
```

#### Step 3: Upgrade pip to latest version
```sh
python -m pip install --upgrade pip
```

#### Step 4: Download and install packages
```sh
pip install openvino==2025.0.0 ultralytics
```

#### Step 5: Download Yolo11 model
Run the python script from [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/yolo_models.md#2-yolov8-yolov9-yolov10-yolo11) to download and convert yolo11 model in Intel OpenVINO format. Replace the `model_name` and `model_type` in the script with relevant value as required for other models.

#### Step 6: Deactivate virtual environment
```sh
deactivate
```

### Run YOLO model

Volume mount YOLO model directory from host to DL Streamer Pipeline Server container by adding below lines to `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml`

```sh
    volumes:
      - "[Path to yolo11s model directory on host]:/home/pipeline-server/yolo_models/yolo11s"
```

Bring up DL Streamer Pipeline Server containers,

Next bring up the containers
```sh
cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker
```

```sh
docker compose up
```

The below CURL command runs the default pipeline with classroom.avi video as source and the downloaded Yolo model for object detection. Metadata is saved to file `/tmp/results.jsonl` and frames are streamed over RTSP accessible at `rtsp://<SYSTEM_IP_ADDRESS>:8554/classroom-video-streaming`.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/classroom.avi",
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
            "path": "classroom-video-streaming"
        }
    },
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/yolo_models/yolo11s/FP32/yolo11s.xml",
            "device": "CPU"
        }
    }
}'
```