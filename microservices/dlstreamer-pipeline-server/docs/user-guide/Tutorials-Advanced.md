# Tutorials Advanced

-   [Get tensor vector data](#get-tensor-vector-data)
-   [Multistream pipelines with shared model instance](#multistream-pipelines-with-shared-model-instance)
-   [Cross stream batching](#cross-stream-batching)
-   [S3 frame storage](#s3-frame-storage)
<!---
-   [Enable Open Telemetry](#enable-open-telemetry)
-->

## Get tensor vector data

EVAM supports extracting tensor data (as python lists) from pipeline models by making use of DLStreamer's `add-tensor-data=true` property for `gvametaconvert` element. Depending upon how gva elements are stacked and whether inference is done on entire frame or on ROIs (Region Of Interest), the metadata json is structured accordingly. Tensor outputs are vector representation of the frame/roi. It can be used by reference applications for various usecases such as image comparison, image description, image classification using custom model, etc. To learn more about the property, read [here](https://dlstreamer.github.io/elements/gvametaconvert.html).

Follow the below steps to publish tensor vector data along with other metadata via MQTT

1. Update default pipeline present in `[EVAM_WORKDIR]/configs/default/config.json` with the pipeline below (edit the path to model xml and proc json to your needs) - 
    `NOTE` The model used in the below pipeline is from [here](https://dlstreamer.github.io/supported_models.html). Please refer the documentation from DLStreamer on how to download it for your usage [here](https://dlstreamer.github.io/dev_guide/model_preparation.html)
    ```sh
    "pipeline": "{auto_source} name=source ! decodebin ! gvadetect model=/home/pipeline-server/omz/intel/person-vehicle-bike-detection-2004/FP32/person-vehicle-bike-detection-2004.xml model-proc=/opt/intel/dlstreamer/samples/gstreamer/model_proc/intel/person-vehicle-bike-detection-2004.json ! queue ! gvainference model=/home/pipeline-server/resources/models/classification/resnet50/FP16/resnet-50-pytorch.xml inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! gvametapublish ! appsink name=destination ",
    ```

    `NOTE` The property `add-tensor-data` for the dlstreamer element gvametaconvert is set to `true`. 

2. Add the following MQTT parameters to `[EVAM_WORKDIR]/configs/default/config.json` as shown below to publish the tensor data along with all other metadata via MQTT. The below section should be present in `[EVAM_WORKDIR]/configs/default/config.json` under `pipelines` section. 

    ```sh
    "mqtt_publisher": {
        "publish_frame": false,
        "topic": "edge_video_analytics_results"
    }
    ```
    `NOTE` Follow instruction in the [Prerequisite section](./Tutorials-Basic.md#prerequisite-for-tutorials) to create a sample configuration file.

    After the above changes, the updated config.json looks something like this.
    
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
                    "pipeline": "{auto_source} name=source ! decodebin ! gvadetect model=/home/pipeline-server/omz/intel/person-vehicle-bike-detection-2004/FP32/person-vehicle-bike-detection-2004.xml model-proc=/opt/intel/dlstreamer/samples/gstreamer/model_proc/intel/person-vehicle-bike-detection-2004.json ! queue ! gvainference model=/home/pipeline-server/resources/models/classification/resnet50/FP16/resnet-50-pytorch.xml inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! gvametapublish ! appsink name=destination ",
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

3. Configure MQTT `host` and `port` present in `[EVAM_WORKDIR]/docker/.env`.
    ```sh
    MQTT_HOST=<mqtt_broker_address>
    MQTT_PORT=1883
    ```

    `NOTE` By default, EVAM provides a MQTT broker as part of the docker compose file. In case, the user wants to use a different broker please update the above variables accordingly. 

4. Allow EVAM to read the above modified configuration. We do this by volume mounting the modified default config.json in `docker-compose.yml` file. To learn more, refer [here](./Tutorials-Basic.md#change-dlstreamer-pipeline).
    ```yaml
    services:
        edge-video-analytics-microservice:
            volumes:
                - "../configs/default/config.json:/home/pipeline-server/config.json"
    ```

5. Start EVAM.
    ```sh
    docker compose up -d
    ```

6. Once started, send the following curl command to launch the pipeline
    ```sh
    curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
        "source": {
            "uri": "file:///home/pipeline-server/resources/videos/person-bicycle-car-detection.mp4",
            "type": "uri"
        }
    }'
    ```

7. You can check the vector output by subscribing to mqtt. You can check this [document](./detailed_usage/publisher/eis_mqtt_publish_doc.md#start-mqtt-subscriber) on how to configure and start mqtt subscriber.

    Here's what a sample metadata for a frame looks like (some data deleted to keep size small).

    ```sh
    {
        "objects": [
            {
                "detection": {
                    "bounding_box": {
                        "x_max": 0.6305969953536987,
                        "x_min": 0.38808196783065796,
                        "y_max": 0.8155133128166199,
                        "y_min": 0.5354097485542297
                    },
                    "confidence": 0.5702379941940308,
                    "label": "vehicle",
                    "label_id": 0
                },
                "h": 121,
                "region_id": 146,
                "roi_type": "vehicle",
                "tensors": [
                    {
                        "confidence": 0.5702379941940308,
                        "label_id": 0,
                        "layer_name": "labels\\boxes",
                        "layout": "ANY",
                        "model_name": "torch-jit-export",
                        "name": "detection",
                        "precision": "UNSPECIFIED"
                    },
                    {
                        "data": [
                            1.1725661754608154,
                            -0.46770259737968445,
                            <omitted data>
                            -0.8607546091079712,
                            1.1693058013916016
                        ],
                        "dims": [
                            1,
                            1000
                        ],
                        "layer_name": "prob",
                        "layout": "ANY",
                        "model_name": "torch_jit",
                        "name": "inference_layer_name:prob",
                        "precision": "FP32"
                    }
                ],
                "w": 186,
                "x": 298,
                "y": 231
            },
            {
                "detection": {
                    "bounding_box": {
                        "x_max": 0.25753622874617577,
                        "x_min": 0.017545249313116074,
                        "y_max": 0.39748281240463257,
                        "y_min": 0.12764209508895874
                    },
                    "confidence": 0.5328243970870972,
                    "label": "vehicle",
                    "label_id": 0
                },
                "h": 117,
                "region_id": 147,
                "roi_type": "vehicle",
                "tensors": [
                    {
                        "confidence": 0.5328243970870972,
                        "label_id": 0,
                        "layer_name": "labels\\boxes",
                        "layout": "ANY",
                        "model_name": "torch-jit-export",
                        "name": "detection",
                        "precision": "UNSPECIFIED"
                    },
                    {
                        "data": [
                            0.5690383911132813,
                            -0.5517100691795349,
                            <omitted data>
                            -0.8780728578567505,
                            1.1474417448043823
                        ],
                        "dims": [
                            1,
                            1000
                        ],
                        "layer_name": "prob",
                        "layout": "ANY",
                        "model_name": "torch_jit",
                        "name": "inference_layer_name:prob",
                        "precision": "FP32"
                    }
                ],
                "w": 184,
                "x": 13,
                "y": 55
            }
        ],
        "resolution": {
            "height": 432,
            "width": 768
        },
        "timestamp": 0
    }
    ```

8. To stop EVAM and other services, run the following.
    ```sh
    docker compose down
    ```

## Multistream pipelines with shared model instance

EVAM can execute multiple input streams in parallel. If streams use the same pipeline configuration, it is recommended to create a shared inference element. The ‘model-instance-id=inst0’ parameter constructs such element. 

`model-instance-id` is an optional property that will hold the model in memory instead of releasing it when the pipeline completes. This improves load time and reduces memory usage when launching the same pipeline multiple times. The model is associated with the given ID to allow subsequent runs to use the same model instance.

```sh
"pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
```

Start the first pipeline with following curl command - 
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
edge-video-analytics-microservice  | FpsCounter(last 1.03sec): total=48.57 fps, number-streams=1, per-stream=48.57 fps
edge-video-analytics-microservice  | FpsCounter(average 40.64sec): total=50.47 fps, number-streams=1, per-stream=50.47 fps
edge-video-analytics-microservice  | FpsCounter(last 1.01sec): total=49.55 fps, number-streams=1, per-stream=49.55 fps
edge-video-analytics-microservice  | FpsCounter(average 41.65sec): total=50.45 fps, number-streams=1, per-stream=50.45 fps
```

You can start the second instance of the same pipeline in parallel by sending the same curl command as above. You can use a different video for second instance by changing `uri` config in above curl request. Now you should be able to see `number-streams=2` in your output.

```sh
edge-video-analytics-microservice  | FpsCounter(last 1.00sec): total=49.97 fps, number-streams=2, per-stream=24.98 fps (23.98, 25.98)
edge-video-analytics-microservice  | FpsCounter(average 14.17sec): total=49.25 fps, number-streams=2, per-stream=24.63 fps (23.50, 25.75)
edge-video-analytics-microservice  | FpsCounter(last 1.00sec): total=48.98 fps, number-streams=2, per-stream=24.49 fps (24.99, 23.99)
edge-video-analytics-microservice  | FpsCounter(average 15.19sec): total=49.24 fps, number-streams=2, per-stream=24.62 fps (23.57, 25.68)
```

## Cross stream batching

EVAM supports grouping multiple frames in single batch during model processing. `batch-size` is an optional parameter to be used which specifies the number of input frames grouped together in a single batch. In the below example, the model processes 4 frames at a time.

```sh
"pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection batch-size=4 model-instance-id=1 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
```

Choosing the right batch size:

* `Real time applications`  Keep the batch-size small to minimize the latency. A larger batch size may cause the initial frames to wait until the batch is completely filled before the model begins processing. Also, large batch size means higher memory utilization
* `High throughput `  Keep the batch-size large to maximize the throughput. Some hardware are suited to process large number of frames in parallel, thus reducing overall time required to process all the frames.

`Note` In a multi stream pipeline with a shared model instance, frames can be grouped into a single batch either from multiple pipelines or exclusively from one pipeline, depending on the timing of arrival of frames from the pipelines.

To verify the effect of batch-size you can check the memory utilization of docker by using command `docker stats`. The memory utilization increases when we load multiple frames in one batch. The stats may vary depending on the underlying hardware. 

You can use the following curl command to start the pipeline - 
``` sh
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

* docker stats with batch-size as 1, no of streams as 1
```sh
CONTAINER ID   NAME                                CPU %     MEM USAGE / LIMIT   MEM %     NET I/O           BLOCK I/O     PIDS
f4355ac7a42e   edge-video-analytics-microservice   283.11%   322.6MiB / 31.18GiB   1.01%     42.8kB / 2.69kB   0B / 573kB    36
```

* docker stats with batch-size as 16, no of streams as 1
```sh
CONTAINER ID   NAME                                CPU %     MEM USAGE / LIMIT   MEM %     NET I/O           BLOCK I/O     PIDS
6a3ccbc9fb44   edge-video-analytics-microservice   281.32%   811.7MiB / 31.18GiB   2.54%     42.5kB / 2.83kB   0B / 0B       37
```

* docker stats with batch-size as 1, no of streams as 4
```sh
CONTAINER ID   NAME                                CPU %     MEM USAGE / LIMIT   MEM %     NET I/O           BLOCK I/O     PIDS
f842a3f617c8   edge-video-analytics-microservice   1169.10%   462.7MiB / 31.18GiB   1.45%     46.3kB / 4.18kB   0B / 352kB    55
```

* docker stats with batch-size as 16, no of streams as 4
```sh
CONTAINER ID   NAME                                CPU %     MEM USAGE / LIMIT   MEM %     NET I/O           BLOCK I/O     PIDS
5b1c3b35ddfe   edge-video-analytics-microservice   1170.64%   999.2MiB / 31.18GiB   3.13%     45.4kB / 4.05kB   0B / 123kB    55
```

## S3 frame storage

EVAM supports storing frames from media source into S3 storage. It supports industry standard S3 APIs. Hence, it will be compatible with any S3 storage of your choice. The server details must be added as a service in EVAM's docker-compose.yml file present at `[EVAM_WORKDIR]/docker/docker-compose.yml`.
In an production deployment, one should get the server details from the system admin.

For the sake of demonstration, we will be using MinIO database as the S3 storage for storing frames. To get started, follow the steps below.

1. Modify environment variables
    - Provide the S3 storage server details and credentials in `[EVAM_WORKDIR]/docker/.env` file.

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

    - Update `no_proxy` environment section of EVAM service by adding `minio-server` container name to `no_proxy` parameter present under `environment` section of `edge-video-analytics-microservice` service.
        ```yaml
        services:
            edge-video-analytics-microservice:
                environment:
                    no_proxy=$no_proxy,multimodal-data-visualization-streaming,${RTSP_CAMERA_IP},minio-server
        ```
        `Note` The value added to `no_proxy` must match with the value of `container_name` specified in the `minio` service section at docker compose file (`[EVAM_WORKDIR]/docker/docker-compose.yml`). In our example, its `minio-server`.

3. Update the default `config.json`. 
    - A sample config has been provided for this demonstration at `[EVAM_WORKDIR]/configs/sample_s3write/config.json`. Replace the contents in default config present at `[EVAM_WORKDIR]/configs/default/config.json` with the contents of the sample config. The config.json looks something like this.
        ```sh
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
                        "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish ! jpegenc ! appsink name=destination",
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
    - The configuration above will allow EVAM to load a pipeline that would run an object detection using dlstreamer element `gvadetect`. Although, the MQTT details are provided in the config.json, the S3 configuration related to the bucket and object path will be sent as part of pipeline launch request mentioned few steps below.

4. Allow EVAM to read the above modified configuration. 
    - We do this by volume mounting the modified default config.json in `docker-compose.yml` file. To learn more, refer [here](./Tutorials-Basic.md#change-dlstreamer-pipeline).
    
        ```yaml
        services:
            edge-video-analytics-microservice:
                volumes:
                    - "../configs/default/config.json:/home/pipeline-server/config.json"
        ```
5. Start EVAM.
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
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    },
    "S3_write": {
        "bucket": "evam",
        "folder_prefix": "camera1",
        "block": false
        }
    }'
    ```
    
    The `S3_write` sections mentions that the frame objects (referred by there respective image handles) will be stored in the bucket `evam` at the object path prefixed as `camera1`. For example `camera1\<IMG_HANDLE>.jpg`. To learn more about the configuration details of S3 storage mentioned in `S3_write`, refer [here](./detailed_usage/publisher/s3_frame_storage.md#s3_write-configuration)

    **Note**: EVAM supports only writing of object data to S3 storage. It does not support creating, maintaining or deletion of buckets. It also does not support reading or deletion of objects from bucket. Also, as mentioned before EVAM assumes that the user already has a S3 storage with buckets configured.

8. Once you start EVAM with above changes, you should be able to see frames written to S3 storage and metadata over MQTT on topic `edge_video_analytics_results` . Since we are using MinIO storage for our demonstration, you can see the frames being written to Minio by logging into MinIO console. You can access the console in your browser - `http://<S3_STORAGE_HOST>:9090`. Use the credentials specified above in the `[EVAM_WORKDIR]/docker/.env` to login into console. After logging into console, you can go to your desired buckets and check the frames stored.

    **Note**: Minio console runs at port 9090 by default.

9. To stop EVAM and other services, run the following. Since the data is stored inside the MinIO container for this demonstration, the frames will not persists after the containers are brought down.

    ```sh
    docker compose down
    ```

<!---
## Enable Open Telemetry

EVAM supports gathering metrics over Open Telemetry. The supported metrics currently are:
- `cpu_usage_percentage`: Tracks CPU usage percentage of EVAM python process
- `memory_usage_bytes`: Tracks memory usage in bytes of EVAM python process
- `fps_per_pipeline`: Tracks FPS for each active pipeline instance in EVAM

There is a dedicated docker compose file for demonstrating Open Telemetry for EVAM. It is available in EVAM's github repository, under the "docker" folder i.e., `[EVAM_WORKDIR]/docker/docker-compose-otel.yml`

The way it works is, EVAM exports the telemetry data to the open telemetry service (otel/opentelemetry-collector-contrib) and then prometheus service scrapes the data which can be visualized. The necessary configuration for open telemetry and prometheus services is located at `[EVAM_WORKDIR]/configs/open_telemetry/otel-collector-config.yaml` and `[EVAM_WORKDIR]/configs/open_telemetry/prometheus.yml` respectively.

Below are the necessary configuration to be aware of (or modify accordingly based on your deployment) in `[EVAM_WORKDIR]/docker/.env` (They will be consumed appropriately in `[EVAM_WORKDIR]/docker/docker-compose-otel.yml`):
```sh
ENABLE_OPEN_TELEMETRY=true # true to enable open telemetry and false otherwise
OTEL_COLLECTOR_HOST=otel-collector # open telemetry container name in `[EVAM_WORKDIR]/docker/docker-compose-otel.yml`. Can also be the IP address of the machine if open telemetry container is running on a different machine. Ex: OTEL_COLLECTOR_HOST=10.10.10.10
OTEL_COLLECTOR_PORT=4318 # Open telemetry container will receive data on this port. If this value is changed, ensure to update `[EVAM_WORKDIR]/configs/open_telemetry/otel-collector-config.yaml` appropriately.
OTEL_EXPORT_INTERVAL_MILLIS=5000 # How often to export metrics to the open telemetry collector in milli seconds.
```

With this information at hand, let us now see open telemetry in action.

- Start the services
    ```sh
        docker compose -f docker-compose-otel.yml up
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

- Open `http://<HOST_IP>:9099/query` in your browser to view the prometheus console and try out the below queries:
    - `cpu_usage_percentage`
    - `memory_usage_bytes`
    - `fps_per_pipeline{}`
        - If you are starting multiple pipelines, then it can also be queried per pipeline ID. Example: `fps_per_pipeline{pipeline_id="658a5260f37d11ef94fc0242ac160005"}`

    ![Open telemetry fps_per_pipeline example in prometheus](./images/prometheus_fps_per_pipeline.png)
-->
