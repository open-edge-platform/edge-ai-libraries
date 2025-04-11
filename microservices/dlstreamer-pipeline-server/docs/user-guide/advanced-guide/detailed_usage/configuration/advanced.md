```{eval-rst}
:orphan:
```
# Advanced DL Streamer Pipeline Server configuration

Basic configuration needs that described [here]. For EIS deployments, there are more fields applicable and they are described in this section. 

Here is a sample EIS config file. 

```sh
{
    "config": {
        "logging": {
            "C_LOG_LEVEL": "INFO",
            "PY_LOG_LEVEL": "INFO"
        },
        "cert_type": [
            "grpc"
        ],
        "pipelines": [
            {
                "name": "dlstreamer_pipeline_results",
                "source": "gstreamer",
                "queue_maxsize": 50,
                "pipeline": "multifilesrc loop=TRUE location=/home/pipeline-server/resources/videos/anomalib_pcb_test.avi name=source ! h264parse ! decodebin ! queue max-size-buffers=10 ! videoconvert ! video/x-raw,format=RGB ! udfloader name=udfloader ! appsink name=destination",
                "parameters": {
                    "type": "object",
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
                },
                "auto_start": true,
                "udfs": {
                    "udfloader": [
                        {
                            "device": "CPU",
                            "task": "classification",
                            "inferencer": "openvino_nomask",
                            "model_metadata": "/home/pipeline-server/udfs/python/anomalib_udf/stfpm/metadata.json",
                            "name": "python.anomalib_udf.inference",
                            "type": "python",
                            "visualize": "false",
                            "weights": "/home/pipeline-server/udfs/python/anomalib_udf/stfpm/model.onnx"
                        }
                    ]
                }
            }
        ]
    },
    "interfaces": {
        "Clients": [
            {
                "EndPoint": "multimodal-data-visualization-streaming:65138",
                "Name": "visualizer",
                "Topics": [
                    "dlstreamer_pipeline_results"
                ],
                "Type": "grpc",
                "overlay_annotation": "true"
            },
            {
                "EndPoint": "ia-datastore:65137",
                "Name": "datastore",
                "Topics": [
                    "dlstreamer_pipeline_results"
                ],
                "Type": "grpc"
            }
        ]
    }
}
```

Fields in `config` section.
|      Parameter      |                                                     Description                                                |
| :-----------------: | -------------------------------------------------------------------------------------------------------------- |

| `cert_type`         | Type of EIS certs to be created. This should be `"zmq"` or `"pem"`.                                      |
| `logging`           | Set log level for `"C_LOG_LEVEL"`, `"PY_LOG_LEVEL"`. Default is `INFO`.                                      |
| `pipelines`         | List of DL Streamer pipelines.     

Fields within `pipelines` section. 
|      Parameter          |                                                     Description                                                |
| :----------------------:| -------------------------------------------------------------------------------------------------------------- |
|`name`                   | Name of the pipeline.                                      |
| `source`                | Source of the frames. This should be `"gstreamer"` or `"image-ingestor"`.                                              |
| `pipeline`              | DL Streamer pipeline description.         |
| `parameters`            | Optional JSON object specifying pipeline parameters that can be customized when the pipeline is launched |
| `auto_start`            | The Boolean flag for whether to start the pipeline on DL Streamer Pipeline Server start up. |
| `udfs`                  | UDF config parameters |
| `tags`                  | Additional information to store with frame metadata. e.g. camera location/orientation of video input. |
| `publish_raw_frame`     | The Boolean flag for whether to publish raw frame.                                  |
| `encoding`              | Encodes the image in jpeg or png format.                                                                       |
| `mqtt_publisher`        | Publishes frame/metadata to mqtt broker.                                                                      |
| `convert_metadata_to_dcaas_format`  | Converts inference results to DCaaS standardized format.

> **Note:**
- For `jpeg` encoding type, level is the quality from 0 to 100. A higher value means better quality.
- For `png` encoding type, level is the compression level from 0 to 9. A higher value means a smaller size and longer compression time.
- Encoding elements can be used in the `pipeline` as an alternative to specifying the `encoding` parameters.
Refer to the below pipeline for using `jpegenc` in config.json.
  ```javascript
  "pipeline": "multifilesrc loop=FALSE stop-index=0 location=/home/pipeline-server/resources/pcb_d2000.avi name=source ! h264parse ! decodebin ! videoconvert ! video/x-raw,format=BGR ! udfloader name=udfloader ! jpegenc ! appsink name=destination",
  ```
- Refer to the below pipeline for using `pngenc` in config.json.
  ```javascript
  "pipeline": "multifilesrc loop=FALSE stop-index=0 location=/home/pipeline-server/resources/pcb_d2000.avi name=source ! h264parse ! decodebin ! videoconvert ! video/x-raw,format=BGR ! udfloader name=udfloader ! videoconvert ! pngenc ! appsink name=destination",
  ```
- `convert_metadata_to_dcaas_format`, when set to `true` in config.json converts the metadata to DCaaS compatible format. Currently this has been tested for `gvadetect` element used in the pipeline.
Refer to the below pipeline for example,
  ```javascript
  "pipeline": "multifilesrc loop=TRUE stop-index=0 location=/home/pipeline-server/resources/classroom.avi name=source ! h264parse ! decodebin ! queue max-size-buffers=10 ! videoconvert ! video/x-raw,format=BGR ! gvadetect model=/home/pipeline-server/models/object_detection/person/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! queue ! jpegenc ! appsink name=destination",
  ```
- For MQTT publishing,

  - Refer to the document [here](../publisher/eis_mqtt_publish_doc.md) for details on prerequisites, configuration, filtering and error handling.

  - MQTT publishing can be enabled along with EII Message Bus publishing.

## Interface Configuration
By default, DL Streamer Pipeline Server is configured to publish frame and metadata over the EIS message bus. The interfaces configuration for publisher is shown below -

```json
    "interfaces": {
        "Clients": [
            {
                "EndPoint": "multimodal-data-visualization-streaming:65138",
                "Name": "visualizer",
                "Topics": [
                    "dlstreamer_pipeline_results"
                ],
                "Type": "grpc",
                "overlay_annotation": "true"
            }
        ]
    }
```

|          Key        |    Type   | Required (Mandatory) |                         Description                          |
| :-----------------: | --------- | -------------------- | ------------------------------------------------------------ |
| `Clients`         | `array`   | Yes                  | Entire client interface will be added with in the array. Multiple server endpoints can be added by adding elements in the array.  |
| `Name`              | `string`  | Yes                  | Name of different publisher interfaces                   |
| `Type`              | `string`  | Yes                  | Specifies protocol on which data will be published. Currently `grpc` is only supported.    |
| `EndPoint`          | `string` or `object`  | Yes                  | Refers to server endpoint which is the container name and the port number. In `network` mode, use host IP instead of container name. For example, when using network cameras. Refer to [Different ways of specifying endpoint](###**Note**-"endpoint"-can-be-given-in-different-ways:)|
| `Topics`            | `array`   | Yes                  | Specifying the topics on which data will be published on. Multiple elements in this array can denote multiple topics published on the same endpoint   |
| `overlay_annotation`    | `string`   | No                  | Can be `true` or `false`(also `false` when key is omitted). Specifies whether to use overlay annotations using annotation data from a UDF. For this to work, the UDF must provide annotation data as part of metadata.|

