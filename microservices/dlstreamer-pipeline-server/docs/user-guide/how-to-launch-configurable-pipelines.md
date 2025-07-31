# How to launch configurable pipelines

Pipelines defined in configuration file can support placeholders. The values for these placeholders can be dynamically provided via REST request. The configuration sections in a pipeline are `source`, `destination` and `parameters`.

>*Note*: Since the parameters are unknown during deployment, these configurable pipelines need a payload with values for the above configurable sections either in the form of a REST request or a `payload` (to enable `autostart`) .

For example, consider the below pipeline from default config:

```sh
    {
        "name": "pallet_defect_detection",
        "source": "gstreamer",
        "queue_maxsize": 50,
        "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
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
```

`{auto_source}` provides source abstraction to specify the source at the time of submitting REST request making pipelines flexible as they the same pipeline can be reused different source types like file, RTSP, webcam etc. To learn more on source abstraction and different supported types, refer to this [section](./advanced-guide/detailed_usage/rest_api/customizing_pipeline_requests.md#source)

`gvametapublish` provides options to send metadata to a chosen destination. For example, metadata can be sent to file, MQTT/Kafka messages brokers. Additionally, DL Streamer Pipeline Server send frames that can be sent over RTSP/WebRTC.
To learn more on setting metadata destination, refer to this [section](./advanced-guide/detailed_usage/rest_api/customizing_pipeline_requests.md#metadata-destination).
To learn more on setting frame destination, refer to this [section](./advanced-guide/detailed_usage/rest_api/customizing_pipeline_requests.md#frame-destination).

`parameters` are an optional section (JSON object) within a pipeline definition and are used to specify which pipeline properties are configurable. In the sample pipeline above, we allow parameterization of `gvadetect` element properties (aliased by setting name=detection). To learn more about pipeline parameters, refer to this [section](./advanced-guide/detailed_usage/rest_api/defining_pipelines.md#pipeline-parameters)

**Note**: Refer this [tutorial](./how-to-change-dlstreamer-pipeline.md) and this [section](./advanced-guide/detailed_usage/configuration/basic.md) for configuration file. 
Refer [this](./advanced-guide/detailed_usage/rest_api/customizing_pipeline_requests.md) page for detailed instructions on how to define configurable pipelines and launch them using REST command.

Here is a sample REST request for the default pipeline (same as above sample) which has placeholders for `source`, `destination` and `parameters`. A video file within the container is specified as source, file is set as metadata destination, RTSP is specified for frame destination and the gvadetect element parameters such as model and device are provided under the parameters section. The model and video files are already provided as DL Streamer Pipeline Server samples.

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
