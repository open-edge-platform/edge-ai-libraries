# Defining and launching preconfigured pipelines 

Pipelines defined in configuration file can be pre configured i.e. they include all the configurations prior to runtime including any `source`, `destination`, `parameters` etc

These pipelines can be auto started during EVAM start up by setting `auto_start` flag to `true`.  Refer to this [tutorial](../Tutorials-Basic.md#change-dlstreamer-pipeline) and this [section](../detailed_usage/configuration/basic.md). 

Here is an example of a pre configured pipeline. The pipeline runs a GeTi trained pallet defect detection model on a sample warehouse video. The detection results are written in `/tmp/results.jsonl` file in JSON format. 

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
                "pipeline": "multifilesrc loop=TRUE location=/home/pipeline-server/resources/videos/warehouse.avi ! h264parse ! decodebin ! videoconvert ! gvadetect name=detection model=/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination method=file file-path=/tmp/results.jsonl ! appsink name=appsink",
                "auto_start": true
            }
        ]
    }
}
```

Alternatively, pre-configured pipelines can also be started via REST request (empty) after setting  `auto_start` flag to `false`

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{}'
```
## Providing `payload` for autostart
In case you have provided placeholders in you pipeline configuration like below, we can also plug in the REST payload in the pipeline configuration and make use of the `auto_start` feature to start EVAM with this pipeline with the payload provided. 

```sh
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
    }

```

The REST payload can be added inside a `payload` key section. The `autostart` is then set `true`. 

The config from above sample will now look like this. Notice `auto_start` has been set to true and REST payload is provided in the `payload` section.

```json
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
        "auto_start": true,
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
    }
```
The pipeline would start automatically as soon as EVAM starts. 

And of course, we can send new curl requests to launch new instances with different payload parameters.
