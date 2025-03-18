# Tutorials Basic
-   [Prerequisite for tutorials](#prerequisite-for-tutorials)
-   [Use REST API](#use-rest-api)
-   [Change DLStreamer Pipeline](#change-dlstreamer-pipeline)
-   [Autostart pipelines](#autostart-pipelines)
-   [User Defined Function (UDF) pipelines](#user-defined-function-udf-pipelines)
-   [Set GPU backend for inferencing](#set-gpu-backend-for-inferencing)
-   [Use RTSP source](#use-rtsp-source)
-   [Use Image file as source](#use-image-file-as-source)
-   [Start MQTT publish of metadata](#start-mqtt-publish-of-metadata-with-gvametapublish)
-   [Download and Run Yolo models](#download-and-run-yolo-models)
<!---   [Create Pipeline to save raw frame on file system]
-   [Create pipeline to save overlayed frame on file system of GETi UDF pipeline]
-   [Create pipeline to save overlayed frame on file system of gvadetect pipeline]
-   [Set MQTT Config and start MQTT publish of metadata and frame]
-   [Start DLStreamer pipeline when EVAM starts]-->

## Prerequisite for tutorials

For tutorials that requires you to update the default configuration of EVAM, please follow the below instruction.

Ensure that you have a `[EVAM_WORKDIR]/configs/default/config.json` file with the below snippet in your workspace (`EVAM_WORKDIR`) on the host machine. The tutorials will take you through updating the configuration accordingly.
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
                "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
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
                "auto_start": false
            }
        ]
    }
}
```

## Use REST API

Refer to the [section](./Get-Started-Guide.md#run-default-sample) to understand the usage of REST API via starting a DLStreamer pipeline that runs object detection, checking running status of this pipeline and stopping the pipeline.
This example also demonstrates saving the resulting metadata to a file and sending frames over RTSP for streaming.

## Change DLStreamer pipeline

EVAM supports dynamic update of pipeline parameters using REST API. Users are required to provide required placeholders in `[EVAM_WORKDIR]/configs/default/config.json` to make it configurable at run-time of EVAM container. Follow instruction in the [Prerequisite section](./Tutorials-Basic.md#prerequisite-for-tutorials) to create a sample configuration file.

In case users want to update default pipeline, they need to update the same in configuration file that EVAM loads. Users can mount updated config files from host systems on to EVAM containers by updating `[EVAM_WORKDIR]/docker/docker-compose.yml`. To get you started, instruction to create sample docker compose file is available [here](./Get-Started-Guide.md#pull-the-image-and-start-container). Refer below snippets:

```sh
    volumes:
      # Volume mount [WORDDIR]/configs/default/config.json to config file that EVAM container loads."
      - "../configs/default/config.json:/home/pipeline-server/config.json"
```
As an example we are creating `video-ingestion and resize` pipeline. We need to update `pipeline` key in `[EVAM_WORKDIR]/configs/default/config.json` as shown below.  It would create DLStreamer pipeline that reads user provided video file, decodes it, and resize to 1280x720.
Note: Follow instruction in the [Prerequisite section](./Tutorials-Basic.md#prerequisite-for-tutorials) to create a sample configuration file.
```sh
"pipeline": "{auto_source} name=source  ! decodebin ! videoscale ! video/x-raw, width=1280,height=720 ! gvametapublish name=destination ! appsink name=appsink",
```
`Note`: If needed users can change pipeline name by updating `name` key in `config.json`. If user is updating this field, accordingly endpoint in curl request needs to be changed to `<SERVER-IP>:<PORT>/pipelines/user_defined_pipelines/<NEW-NAME>`. In this example, we are only changing pipeline.

Once update, user needs to restart EVAM containers to reflect this change. Run these commands from `[EVAM_WORKDIR]/docker/` folder.
Note: To get you started, instruction to create sample docker compose file is available [here](./Get-Started-Guide.md#pull-the-image-and-start-container)

```sh
docker compose down

docker compose up
```

Above steps will restart EVAM and load `video-ingestion and resize` pipeline. Now to start this pipeline, run below Curl request. It would start DLStreamer pipeline that reads `classroom.avi` video file with resolution of 1920x1080 and after resizing to 1280x720, it would stream over RTSP. Users can view this on any media player e.g. vlc, ffplay etc.

RTSP Stream will be accessible at `rtsp://<SYSTEM_IP_ADDRESS>:8554/classroom-video-streaming`.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
                "source": {
                    "uri": "file:///home/pipeline-server/resources/classroom.avi",
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
                }
}'
```

## Autostart pipelines

EVAM allows autostarting pipelines provided all the necessary payload information such as source, destination, model parameters etc are available in the configuration file.

There are 2 ways to enable the autostart. First way is to provide all the necessary payload information while defining the pipeline itself. Second way is to provide the information under the `"pipelines"` config with `"payload"` as the keyword.

Autostart for a pipeline can be enabled by setting the flag `auto_start` to `true`. This would start an instance of pipeline immediately as soon as EVAM container is up.

### Method 1 - Specifying all the information in the pipeline itself - 

Replace the following sections in `[EVAM_WORKDIR]/configs/default/config.json` with the following
Note: Follow instruction in the [Prerequisite section](./Tutorials-Basic.md#prerequisite-for-tutorials) to create a sample configuration file.

- replace `"pipeline"` section with  

    ```sh
    "pipeline": "multifilesrc location=/home/pipeline-server/resources/videos/warehouse.avi name=source  ! decodebin ! videoconvert ! gvadetect model=/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml name=detection ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish file-format=json-lines file-path=/tmp/results.jsonl name=destination ! appsink name=appsink",
    ```
- set `"auto_start"`to `"true"`.

Notice that we have inlined model xml path (in `gvadetect` element) and metadata publish file (in `gvametapublish` element) into the pipeline string.

### Method 2 - Write all parameters under `"pipelines"` config with `"payload"` as keyword

- Use default `"pipeline"` and add necessary information such as source, destination and model path as a json object under `"payload"` keyword. `"payload"` config needs to be present inside `"pipelines"` config. Example shown below - 

```sh
"payload": {
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
}
```

- set `"auto_start"`to `"true"`.

You can choose either method with the autostart pipeline. After making changes to config.json, make sure to save it and restart EVAM. Ensure that the changes made to the config.json are reflected in the container by volume mounting (as mentioned [above](#change-dlstreamer-pipeline)) it.

```sh
    cd [EVAM_WORKDIR]/docker/
    docker compose down
    docker compose up
```

`Note` If `"auto_start"`to `"false"`, then you can start the pipeline manually by sending the curl request as shown below. In this case, curl request need not have any parameters as all the required parameters to start the pipeline is already mentioned in the pipeline config above.

```sh
curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{}'
```

We should see the metadata results in `/tmp/results.jsonl` file like the following snippet.

```sh
{"objects":[{"detection":{"bounding_box":{"x_max":0.2760509825893678,"x_min":0.0009660996147431433,"y_max":0.5821986049413681,"y_min":0.23702500760555267},"confidence":0.8490034937858582,"label":"box","label_id":0},"h":166,"region_id":4602,"roi_type":"box","w":176,"x":1,"y":114},{"detection":{"bounding_box":{"x_max":0.18180961161851883,"x_min":0.051308222115039825,"y_max":0.4810962677001953,"y_min":0.3541457951068878},"confidence":0.7778390645980835,"label":"defect","label_id":2},"h":61,"region_id":4603,"roi_type":"defect","w":84,"x":33,"y":170}],"resolution":{"height":480,"width":640},"tags":{},"timestamp":96862470800}
{"objects":[{"detection":{"bounding_box":{"x_max":0.2759847411653027,"x_min":0.0009118685266003013,"y_max":0.5828713774681091,"y_min":0.2364599108695984},"confidence":0.8393885493278503,"label":"box","label_id":0},"h":166,"region_id":4606,"roi_type":"box","w":176,"x":1,"y":114},{"detection":{"bounding_box":{"x_max":0.18369046971201897,"x_min":0.044871505349874496,"y_max":0.480486124753952,"y_min":0.34511199593544006},"confidence":0.7414445281028748,"label":"defect","label_id":2},"h":65,"region_id":4607,"roi_type":"defect","w":89,"x":29,"y":166}],"resolution":{"height":480,"width":640},"tags":{},"timestamp":96895871652}
```

## User Defined Function (UDF) pipelines
EVAM supports udfloader element which allow user to write an User Defined Function (UDF) that can transform video frames and/or manipulate metadata. You can do this by adding an element called 'udfloader'. You can try simple udfloader pipeline by replacing the following sections in [EVAM_WORKDIR]/configs/default/config.json with the following
Note: Follow instruction in the [Prerequisite section](./Tutorials-Basic.md#prerequisite-for-tutorials) to create a sample configuration file.

- replace `"pipeline"` section with  

    ```sh
    "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! video/x-raw,format=RGB ! udfloader name=udfloader ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
    ```

- replace `"properties"` section with  

    ```sh
    "properties": {
        "udfloader": {
            "element": {
                "name": "udfloader",
                "property": "config",
                "format": "json"
            },
            "type": "object"
        }
    }
    ```

- add `"udfs"` section in config (after `"parameters"`)  

    ```sh
    "udfs": {
        "udfloader": [
            {
                "name": "python.geti_udf.geti_udf",
                "type": "python",
                "device": "CPU",
                "visualize": "true",
                "deployment": "./resources/models/geti/pallet_defect_detection/deployment",
                "metadata_converter": "null"
            }
        ]
    }
    ```
Save the config.json and restart EVAM
Ensure that the changes made to the config.json are reflected in the container by volume mounting (as mentioned [above](#change-dlstreamer-pipeline)) it.

```sh
    cd [EVAM_WORKDIR]/docker/
    docker compose down
    docker compose up
```

Now to start this pipeline, run below Curl request

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
        "udfloader": {
            "udfs": [
                {
                    "name": "python.geti_udf.geti_udf",
                    "type": "python",
                    "device": "CPU",
                    "visualize": "true",
                    "deployment": "./resources/models/geti/pallet_defect_detection/deployment",
                    "metadata_converter": "null"
                }
            ]
        }
    }
}'
```

`Note` The `"udfloader"` config needs to be present in either config.json or in the curl command. It is not needed at both places. However, if specified at both places then the config in curl command will override the config present in config.json

We should see the metadata results in `/tmp/results.jsonl`

For more details on UDF, you can refer this [document](./detailed_usage/udf/Overview.md)

## Set GPU backend for inferencing

For inferencing with GPU backend, we will use the REST API to start a pipeline.


Replace the following sections in `[EVAM_WORKDIR]/configs/default/config.json` with the following
Note: Follow instruction in the [Prerequisite section](./Tutorials-Basic.md#prerequisite-for-tutorials) to create a sample configuration file.

- replace `"pipeline"` section with  
    ```sh
    "pipeline": "{auto_source} name=source  ! parsebin ! vah264dec ! video/x-raw(memory:VAMemory) ! gvadetect name=detection pre-process-backend=va  ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
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
Save the config.json and restart EVAM
Ensure that the changes made to the config.json are reflected in the container by volume mounting (as mentioned [above](#change-dlstreamer-pipeline)) it.

```sh
    cd [EVAM_WORKDIR]/docker/
    docker compose down
    docker compose up
```
We should see the metadata results in `/tmp/results.jsonl` file like in previous tutorial.


## Use RTSP source

You can either start a RTSP server to feed video or you can use RTSP stream from a camera and accordingly update the `uri` key in following request to start default pallet defect detection pipeline. 

Similar to default EVAM pipeline, it publishes metadata to a file `/tmp/results.jsonl` and sends frames over RTSP for streaming. 

RTSP Stream will be accessible at `rtsp://<SYSTEM_IP_ADDRESS>:8554/pallet-defect-detection`.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "uri": "rtsp://<ip_address>:<port>/<server_url>",
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

For more details on RTSP, you can refer this [document](./detailed_usage/camera/rtsp.md)

## Use image file as source

Pipeline requests can also be sent on demand for an image file source on an already queued pipeline. It is only supported for source type: `"image-ingestor"`. 

There are two steps to run image ingestor.
1. First, a pipeline is queued that loads the pipeline and configures the request type to be asynchronous or synchronous in order. This prepares the pipeline for the image requests to follow. This would set the pipeline to enter in `QUEUED` state and wait for requests.
2. Secondly, individual image requests are then sent to this queued pipeline to fetch the metadata or image blob, which can be either in the response or some other destination.

### Asynchronous vs Synchronous behavior
Image request can be run in 2 modes - *sync* and *async*. This configuration is set while pipeline is queued.

* `"sync":true`  config is used when we want the output to be displayed as response for post request
* `"sync":false`  config is used when we want to have more control on the output.

### Async mode

By default, image ingestor runs in async mode i.e. `sync` is `false`.
A sample config has been provided in below snippet:
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
                "source": "image_ingestor",
                "queue_maxsize": 50,
                "pipeline": "appsrc name=source ! decodebin ! videoconvert ! videoscale ! gvadetect name=detection ! queue ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
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
                "auto_start": false
            }
        ]
    }
}

```

Follow [this tutorial](./Tutorials-Basic.md#change-dlstreamer-pipeline) to launch EVAM with above config. 

Pipeline can be started by the following request. This would set the pipeline in queued state to wait for images requests. Here is a sample request to queue the pipeline in asynchronous mode i.e. `sync`:`false` (default if omitted)

`Note` that source is not needed to start the pipeline, only destination and other parameters. Destination is required only when "*sync*" config is set to false.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "sync": false,
    "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results1.jsonl",
            "format": "json-lines"
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
Once the pipeline has started, we would receive an instance id (e.g. `9b041988436c11ef8e690242c0a82003`). We can use this instance id to send inference requests for images as shown below. Replace the `{instance_id}` to the id you would have received as a response from the previous POST request.

Note that only source section is needed for the image files to send infer requests. Make sure that EVAM has access to the source file preferably by volume mounting in `docker-compose.yml`.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection/{instance_id} -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "path": "/home/pipeline-server/resources/images/classroom.jpg",
        "type": "file"
    }
}'
```
Note: The path in the above command `/home/pipeline-server/resources/images/classroom.jpg` is not a part of EVAM docker image and is for the sake of explanation only. If you would like to actually use this path (classroom.jpg image), it is available in EVAM's github repo, under the "resources" folder and should be appropriately volume mounted to EVAM container in its docker compose file.
Example:
```sh
    volumes:
      - "../resources:/home/pipeline-server/resources/"  
```
Alternatively, you can appropriately volume mount a .jpg image of your choice.
To get you started, sample docker compose file is available [here](./Get-Started-Guide.md#pull-the-image-and-start-container)

The output metadata will be available in the destination provided while queuing the pipeline, which is `/tmp/results.jsonl`.
Users can make as many request to the queued pipeline until the pipeline has been explicitly stopped.

### Sync mode

Another way of queuing a image ingestor pipeline is in synchronous mode. The pipeline destination should be compatible to support this mode i.e. the destination should be `appsink`. A sample config has been provided in below snippet:
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
                "source": "image_ingestor",
                "queue_maxsize": 50,
                "pipeline": "appsrc name=source  ! decodebin  ! videoconvert ! videoscale ! gvadetect name=detection ! queue ! gvametaconvert add-empty-results=true name=metaconvert ! appsink name=destination",
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
                "auto_start": false
            }
        ]
    }
}

```

Follow [this tutorial](./Tutorials-Basic.md#change-dlstreamer-pipeline) to launch EVAM with above config. 

Pipeline for sync mode can be started by sending the following curl request 
```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "sync": true,
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
}'
```

Once the pipeline is queued, we will receive an instance id. Use this instance id to send inference requests for images as shown below. Have shared a sample request below. 

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection/{instance_id} -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "path": "/home/pipeline-server/resources/images/classroom.jpg",
        "type": "file"
    },
    "publish_frame":true,
    "timeout":10
}'
```
Note: The path in the above command `/home/pipeline-server/resources/images/classroom.jpg` is not a part of EVAM docker image and is for the sake of explanation only. If you would like to actually use this path (classroom.jpg image), it is available in EVAM's github repo, under the "resources" folder and should be appropriately volume mounted to EVAM container in its docker compose file.
Example:
```sh
    volumes:
      - "../resources:/home/pipeline-server/resources/"  
```
Alternatively, you can appropriately volume mount a .jpg image of your choice.
To get you started, sample docker compose file is available [here](./Get-Started-Guide.md#pull-the-image-and-start-container)

Since the pipeline is queued for sync requests, the inference results will be shown in response for post request. Here is a sample response

```json
{
	"metadata": {
		"height": 480,
		"width": 820,
		"channels": 4,
		"source_path": "file:///root/image-examples/example.png",
		"caps": "video/x-raw, width=(int)820, height=(int)468",
		"OTHER_METADATA": {
			"other": "additional pipeline meta data"
		}
	},
	"blobs": "=8HJLhxhj77XHMHxilNKjbjhBbnkjkjBhbjLnjbKJ80n0090u9lmlnBJoiGjJKBK=76788GhjbhjK"
}
```

To learn more on different configurations supported by the request, you can refer [this section](./detailed_usage/rest_api/restful_microservice_interfaces.md/#synchronous-behavior) 


## Start MQTT publish of metadata with `gvametapublish`

The below CURL command publishes metadata to a MQTT broker and sends frames over RTSP for streaming.

 Replace the `<SYSTEM_IP_ADDRESS>` field with your system IP address. 
>Note: When bringing up EVAM containers using `docker compose up`, MQTT broker is also started listening on port `1883`. 

RTSP Stream will be accessible at `rtsp://<SYSTEM_IP_ADDRESS>:8554/pallet_defect_detection`.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
                "source": {
                    "uri": "file:///home/pipeline-server/resources/warehouse.avi",
                    "type": "uri"
                },
                "destination": {
                    "metadata": {
                        "type": "mqtt",
                        "host": "<SYSTEM_IP_ADDRESS>:1883",
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

For more details on MQTT you can refer this [document](./detailed_usage/publisher/eis_mqtt_publish_doc.md)




## Download and Run YOLO models

This tutorial shows how to download YOLO models (YOLOv8, YOLOv9, YOLOv10, YOLO11) and run as part of object detection pipeline. 

For downloading all supported YOLO models and converting them to OpenVINO IR format, please refer to this [document](https://dlstreamer.github.io/dev_guide/yolo_models.html).

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
Run the python script from [here](https://dlstreamer.github.io/dev_guide/yolo_models.html#yolov8-yolov9-yolov10-yolo11) to download and convert yolo11 model in Intel OpenVINO format. Replace the `model_name` and `model_type` in the script with relevant value as required for other models. 

#### Step 6: Deactivate virtual environment 
```sh
deactivate
```

### Run YOLO model

Volume mount YOLO model directory from host to EVAM container by adding below lines to `[EVAM_WORKDIR]/docker/docker-compose.yml`

```sh
    volumes:
      - "[Path to yolo11s model directory on host]:/home/pipeline-server/yolo_models/yolo11s"
```

Bring up EVAM containers,

Next bring up the containers
```sh
cd [EVAM_WORKDIR]/docker
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

