# Video Ingestion based on EVAM

This project demonstrates video ingestion and processing using Deep Learning Streamer Pipeline Server with RabbitMQ (MQTT protocol) for message brokering and minio for object storage.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Setup Environment Variables](#setup-environment-variables)
3. [Download and Convert Models to OpenVINO IR format](#download-models)
4. [Run the Containers](#run-the-containers)
5. [Run the Sample Pipeline](#run-the-sample-pipeline)
6. [Running Tests](#running-tests)
7. [Additional Information](#additional-information)

## Prerequisites

- Docker and Docker Compose installed on your system.
- Set up environment variables for RabbitMQ/minio credentials.

## Build the Video Ingestion Service

1. Clone the repo and change to `video_ingestion` component directory:

    ```bash
    # Clone the latest on mainline
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
    # Alternatively, Clone a specific release branch
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
    
    cd edge-ai-libraries/sample-applications/video-search-and-summarization/video-ingestion
    ```
2. Download and Convert Models to OpenVINO IR format

This repository uses a custom script to download and convert models like [yoloworld](https://docs.ultralytics.com/models/yolo-world/) to the OpenVINO supported format. 
Ensure you have Python installed and run the following commands to execute the script.

2.1. Create a virtual environment.

```sh
python -m venv ov_env
```

2.2 Activate the virtual environment

```sh
source ov_env/bin/activate
```
2.3. Download and install dependencies 

```sh
pip install -q "openvino>=2025.0.0" "nncf>=2.9.0"
pip install -q "torch>=2.1" "torchvision>=0.16" "ultralytics==8.3.59" onnx tqdm opencv-python --extra-index-url https://download.pytorch.org/whl/cpu
```
2.4. Download the models

Convert the default model (yolov8l-worldv2):
```sh
python resources/scripts/converter.py
```

**Advanced Usage**:

The script accepts command-line arguments to customize the conversion:

```sh
python resources/scripts/converter.py --model-name yolov8l-worldv2 --model-type yolo_v8 --output-dir ov_models/yoloworld
```

Available arguments:
- `--model-name`: Name of the model without extension (default: 'yolov8l-worldv2')
- `--model-type`: Type of model (default: 'yolo_v8')
- `--output-dir`: Directory to save the converted models (default: 'models/yoloworld')

2.5. Deacticvate

```sh
deactivate
```

3. Set the credentials for **RabbitMQ** and **Minio** Service by running following commands. You can use any desired value instead of example values being set here:

    ```bash
    export RABBITMQ_DEFAULT_USER=rabbitmq
    export RABBITMQ_DEFAULT_PASS=rabbitmq
    export MINIO_ROOT_USER=minio
    export MINIO_ROOT_PASSWORD=minio_minio
    ```

    > **IMPORTANT :** Please note that docker compose deployment will fail, if above-mentioned variables are not set.

4. **_(Optional)_** Docker Compose builds the _Video Ingestion Service_ with a default image and tag name. If you want to use a different image and tag, export these variables:

    ```bash
    export REGISTRY_URL="your_container_registry_url"
    export PROJECT_NAME="your_project_name"
    export TAG="your_tag"
    ```

    > **_NOTE:_** `PROJECT_NAME` will be suffixed to `REGISTRY_URL` to create a namespaced url. Final image name will be created by further suffixing the application name and tag with the namespaced url. 

    > **_EXAMPLE:_** If variables are set using above command, the final image name for _Video Ingestion Service_ would be `your_container_registry_url/your_project_name/video-ingestion:your_tag`. If variables are not set, in that case, the `TAG` will have default value as _latest_. Hence, final image will be : `video-ingestion:latest`. 

5. Run this to auto-setup all the required variables for deployment:

    ```bash
    source setup.sh
    ```

6. Build the service and run the containers.

    ```bash
    docker compose -f docker/compose.yml up -d --build
    ```

This will start the following services:
- Video Ingestion Service (Based on EVAM)
- RabbitMQ (with MQTT enabled)
- MinIO (for object storage)

## Run the Sample Pipeline

Upload the video to the MinIO server before running the pipeline. Follow these steps to upload the video and make the bucket public:

1. **Access MinIO Console**:
  Open your web browser and navigate to the MinIO console using the URL provided by following command:
    ```bash
    echo http://${host_ip}:${MINIO_CONSOLE_HOST_PORT}
    ```
  Log in using the `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` credentials.(As set in `generate_env.sh`)

2. **Create a Bucket**:
  In the MinIO console, create a new bucket with name : `videosummtest-1`

3. **Upload the Video**:
  Upload video files to the newly created bucket. A sample video file `store-aisle-detection.mp4` can be found in `resources/videos` directory of the repo. We will use the same video for this example.

4. **Make the Bucket Public**:
  To make the bucket public, follow these steps:
  - Go to the bucket settings.
  - Set the bucket policy to allow public read access.


To run a sample pipeline, use the following `curl` command.


> **NOTE :** If you have uploaded a video other than mentioned in the example, replace the video name in `location` field of the request below, with the video of your choice.

```bash
curl http://${host_ip}:${EVAM_HOST_PORT}/pipelines/user_defined_pipelines/object_detection \
  -H 'Content-Type: application/json' \
  -d '{
    "source": {
      "element": "curlhttpsrc",
      "type": "gst",
      "properties": {
          "location": "http://minio:9000/videosummtest-1/store-aisle-detection.mp4"
        }
    },
    "parameters": {
      "frame": 2,
      "chunk_duration": 10,
      "frame_width": 480,
      "detection-properties": {
        "model": "/home/pipeline-server/models/yoloworld/FP32/yolov8l-worldv2.xml",
        "device": "CPU"
      },
      "publish": {
        "minio_bucket": "videosummtest-1",
        "video_identifier": "video_id_1",
        "topic": "topic/video_stream"
      }
    }
  }'
```

> **_NOTE:_** You can tweak `frame`, `chunk_duration` and `frame_width` parameter in above curl request to get results with different accuracy. However, note that increasing the `frame` and `frame_width` will cause significant performance degradation. 

> Also note, these parameters have minimum and maximum allowed value defined. For any invalid value outside the allowed limit, pipeline will fail. Please refer to `resources\conf\config.json` file to verify the permitted values for these parameters in JSON Schema.

Once the pipeline starts, you will receive a UUID (ex: b729ce2ef34711ef99eb0242ac170004) that you can use to track the pipeline's statistics. The metadata generated during the pipeline execution will be sent to the RabbitMQ queue. Additionally, the processed video frames and a `metadata.json` file will be stored in the specified MinIO bucket. 

To view the frames and metadata:
1. Log in to the MinIO console using your credentials.
2. Navigate to the bucket where the frames and metadata are stored.
3. You will find the frames and `metadata.json` file within the bucket.

This setup allows you to monitor and analyze the processed video data efficiently.

> Note: Due to current limitations in EVAM, the `frame` and `interval` values need to be specified in two different sections of the pipeline configuration.

This command will start the Video ingestion object detection pipeline using the specified video file and model, and publish the results RabbitMQ queue to the specified topic.

## Running Tests

The video ingestion component includes comprehensive unit tests. Please install the test dependencies from requirements-test.txt:

```bash
pip install -r requirements-test.txt
```

Then run:
```bash
python -m pytest tests/ -v --cov=src --cov-report=term
```

## Additional Information

- The `compose.yml` file is configured to mount necessary volumes and set up network configurations.
- Ensure that the paths to models and resources in the `compose.yml` file are correctly set up according to your environment.