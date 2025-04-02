# How to publish frames to S3

## Steps

EVAM supports storing frames from media source into an S3 compatible storage. It supports industry standard S3 APIs, thus making it compatible with any S3 storage of your choice. 

First you must add server configuration details such as host, port, credentials, etc. as environment variables to EVAM. 

If you are launching the service along with EVAM, you should add the S3 storage server service details to EVAM's docker-compose.yml file present at `[EVAM_WORKDIR]/docker/docker-compose.yml`. For this tutorial we will be following this approach.

> **Note** In an production deployment, you should get the server details from your system admin and update the environment variables or compose file accordingly.

For the sake of demonstration, we will be using MinIO database as the S3 storage for storing frames and will be launched together with EVAM. To get started, follow the steps below.

1. Modify environment variables in `[EVAM_WORKDIR]/docker/.env` file.
    - Provide the S3 storage server details and credentials.

        ```sh
        S3_STORAGE_HOST=minio-server
        S3_STORAGE_PORT=9000
        S3_STORAGE_USER=<DATABASE USERNAME> #example S3_STORAGE_USER=minioadmin
        S3_STORAGE_PASS=<DATABASE PASSWORD> #example S3_STORAGE_PASS=minioadmin
        ```
    - For metadata publishing, we would be using MQTT. To enable it, we need to add the host and port details of MQTT broker in `.env` file mentioned above.
        ```sh
        MQTT_HOST=<MQTT_BROKER_IP_ADDRESS>
        MQTT_PORT=1883
        ```
        **Note** the default compose file from EVAM provides an MQTT broker already. If you already have a broker running, only the host and port details are to be added to the environment variables.

2. Add minio service to the docker compose yml.
    - Modify the docker-compose.yml file with the following changes. Add `minio` service under `services` section. Modify the values as per your requirements. The user and passwords are fetched from `.env` file updated in the previous step.

        ```yaml
        services:
          minio:
            image: minio/minio:latest  
            hostname: minio-server
            container_name: minio-server
            ports:
              - "9000:9000"  # S3 API
              - "9090:9090"  # MinIO Console UI
            environment:
              MINIO_ROOT_USER: ${S3_STORAGE_USER}  
              MINIO_ROOT_PASSWORD: ${S3_STORAGE_PASS}
            networks:
              - app_network
            command: server --console-address ":9090" /data
        ```

    - Update `no_proxy` environment section of EVAM service by adding `minio-server` container name to `no_proxy` parameter present under `environment` section of `edge-video-analytics-microservice` service. Also include the S3 and MQTT environment variables.
        ```yaml
        services:
          edge-video-analytics-microservice:
            environment:
              - no_proxy=$no_proxy,multimodal-data-visualization-streaming,${RTSP_CAMERA_IP},minio-server
              - S3_STORAGE_HOST=${S3_STORAGE_HOST}
              - S3_STORAGE_PORT=${S3_STORAGE_PORT}
              - S3_STORAGE_USER=${S3_STORAGE_USER}
              - S3_STORAGE_PASS=${S3_STORAGE_PASS}
              - MQTT_HOST=${MQTT_HOST}
              - MQTT_PORT=${MQTT_PORT}
        ```
        
        > **Note** The value added to `no_proxy` must match with the value of `container_name` specified in the `minio` service section at docker compose file (`[EVAM_WORKDIR]/docker/docker-compose.yml`). In our example, its `minio-server`.

3. Update the default `config.json`. 
    - A sample config has been provided for this demonstration at `[EVAM_WORKDIR]/configs/sample_s3write/config.json`. Replace the contents in default config present at `[EVAM_WORKDIR]/configs/default/config.json` with the contents of the sample config. The config.json looks something like this.
        ```json
        {
            "config": {
                "logging": {
                    "C_LOG_LEVEL": "INFO",
                    "PY_LOG_LEVEL": "INFO"
                },
                "pipelines": [
                    {
                        "name": "pallet_defect_detection",
                        "source": "gstreamer",
                        "queue_maxsize": 50,
                        "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! jpegenc ! appsink name=destination",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "detection-properties": {
                                    "element": {
                                        "name": "detection",
                                        "format": "element-properties"
                                    }
                                }
                            }
                        },
                        "auto_start": false,
                        "mqtt_publisher": {
                            "publish_frame": false,
                            "topic": "edge_video_analytics_results"
                        }
                    }
                ]
            }
        }
        ```
        > **Note** Please note that there is no `gvawatermark` element in the pipeline string, which means unannotated frames will be being published to S3 storage. If you wish to publish annotated frames, consider adding it to your pipeline. In that case, the `"pipeline"` string may look like this.
        ```sh
         "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvafpscounter ! gvawatermark ! gvametaconvert add-empty-results=true name=metaconvert ! jpegenc ! appsink name=destination",
        ```

    - The configuration above will allow EVAM to load a pipeline that would run an object detection using dlstreamer element `gvadetect`. Although, the MQTT details are provided in the config.json, the S3 configuration related to the bucket and object path will be sent as part of pipeline launch request mentioned few steps below. To know more about mqtt publishing, refer [here](../user-guide/advanced-guide/detailed_usage/publisher/eis_mqtt_publish_doc.md).

4. Allow EVAM to read the above modified configuration. 
    - We do this by volume mounting the modified default config.json in `docker-compose.yml` file. To learn more, refer [here](how-to-change-dlstreamer-pipeline.md).

        ```yaml
        services:
          edge-video-analytics-microservice:
            volumes:
              - "../configs/default/config.json:/home/pipeline-server/config.json"
        ```
5. Start EVAM and MinIO.
    ```sh
    docker compose up -d
    ```
6. Create MinIO bucket.
    - EVAM expects a bucket to be created before launching the pipeline. 
    Here's is a sample python script (requires `boto3` python package) that would connect to the minio server running and create a bucket named `evam`. This is the bucket we will be using to put frame objects to. Modify the parameters according to the MinIO server configured.
        ```python
        import boto3
        url = "http://localhost:9000"
        user = "minioadmin"
        password = "minioadmin"
        bucket_name = "evam"
        client= boto3.client(
                    "s3",
                    endpoint_url=url,
                    aws_access_key_id=user,
                    aws_secret_access_key=password
        )
        client.create_bucket(Bucket=bucket_name)
        buckets = client.list_buckets()
        print("Buckets:", [b["Name"] for b in buckets.get("Buckets", [])])
        ```
    - Execute it in a python environment that has `boto3` package installed. Save the python script above as `create_bucket.py` in your current directory.
        ```sh
        python3 create_bucket.py
        ```
7. Launch pipeline by sending the following curl request.
    ``` sh
    curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "frame": [
            {
                "type": "s3_write",
                "bucket": "evam",
                "folder_prefix": "camera",
                "block": false
            }
        ]
    },
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
    }'
    ```
    
    The `S3_write` sections mentions that the frame objects (referred by there respective image handles) will be stored in the bucket `evam` at the object path prefixed as `camera1`. For example `camera1\<IMG_HANDLE>.jpg`. To learn more about the configuration details of S3 storage mentioned in `S3_write`, refer [here](./advanced-guide/detailed_usage/publisher/s3_frame_storage.md#s3_write-configuration)
    
    **Note**: EVAM supports only writing of object data to S3 storage. It does not support creating, maintaining or deletion of buckets. It also does not support reading or deletion of objects from bucket. Also, as mentioned before EVAM assumes that the user already has a S3 storage with buckets configured.
8. Once you start EVAM with above changes, you should be able to see frames written to S3 storage and metadata over MQTT on topic `edge_video_analytics_results` . Since we are using MinIO storage for our demonstration, you can see the frames being written to Minio by logging into MinIO console. You can access the console in your browser - `http://<S3_STORAGE_HOST>:9090`. Use the credentials specified above in the `[EVAM_WORKDIR]/docker/.env` to login into console. After logging into console, you can go to your desired buckets and check the frames stored.
    
    **Note**: Minio console runs at port 9090 by default.
9. To stop EVAM and other services, run the following. Since the data is stored inside the MinIO container for this demonstration, the frames will not persists after the containers are brought down.
    ```sh
    docker compose down
    ```