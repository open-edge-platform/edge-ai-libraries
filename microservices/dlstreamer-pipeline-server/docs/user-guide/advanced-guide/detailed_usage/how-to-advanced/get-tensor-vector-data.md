# Get tensor vector data

DL Streamer Pipeline Server supports extracting tensor data (as python lists) from pipeline models by making use of DL Streamer's `add-tensor-data=true` property for `gvametaconvert` element. Depending upon how gva elements are stacked and whether inference is done on entire frame or on ROIs (Region Of Interest), the metadata json is structured accordingly. Tensor outputs are vector representation of the frame/roi. It can be used by reference applications for various use cases such as image comparison, image description, image classification using custom model, etc. To learn more about the element, including its properties, read [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/elements/gvametaconvert.md).

Follow the below steps to publish tensor vector data along with other metadata via MQTT

1. A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_mqtt_publisher/config.json`. We need to volume mount the sample config file in `docker-compose.yml` file. Refer below snippets:

```sh
    volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_mqtt_publisher/config.json to config file that DL Streamer Pipeline Server container loads.
      - "../configs/sample_mqtt_publisher/config.json:/home/pipeline-server/config.json"
```

2. Update pipeline present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_mqtt_publisher/config.json` with the pipeline below (edit the path to model xml and proc json to your needs) -
    `NOTE` The model used in the below pipeline is from [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/supported_models.md). Please refer the documentation from DL Streamer on how to download it for your usage [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/model_preparation.md)

    ```sh
    "pipeline": "{auto_source} name=source ! decodebin ! gvadetect model=/home/pipeline-server/omz/intel/person-vehicle-bike-detection-2004/FP32/person-vehicle-bike-detection-2004.xml model-proc=/opt/intel/dlstreamer/samples/gstreamer/model_proc/intel/person-vehicle-bike-detection-2004.json ! queue ! gvainference model=/home/pipeline-server/resources/models/classification/resnet50/FP16/resnet-50-pytorch.xml inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! gvametapublish ! appsink name=destination ",
    ```

    `NOTE` The property `add-tensor-data` for the dlstreamer element gvametaconvert is set to `true`.

3. Configure MQTT `host` and `port` present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env`.
    ```sh
    MQTT_HOST=<mqtt_broker_address>
    MQTT_PORT=1883
    ```

    `NOTE` By default, DL Streamer Pipeline Server provides a MQTT broker as part of the docker compose file. In case, the user wants to use a different broker please update the above variables accordingly.

4. Start DL Streamer Pipeline Server.
    ```sh
    docker compose up -d
    ```

5. Once started, send the following curl command to launch the pipeline
    ```sh
    curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
        "source": {
            "uri": "file:///home/pipeline-server/resources/videos/person-bicycle-car-detection.mp4",
            "type": "uri"
        }
    }'
    ```

6. You can check the vector output by subscribing to mqtt. You can check this [document](./../../detailed_usage/publisher/eis_mqtt_publish_doc.md#start-mqtt-subscriber) on how to configure and start mqtt subscriber.

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
7. To stop DL Streamer Pipeline Server and other services, run the following.
    ```sh
    docker compose down
    ```
