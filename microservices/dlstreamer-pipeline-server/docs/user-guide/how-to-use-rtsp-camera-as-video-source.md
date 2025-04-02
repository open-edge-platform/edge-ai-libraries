# How to use RTSP camera as a source

* [RTSP Cameras](#rtsp-cameras)
* [Using RTSP as a source](#using-rtsp-as-a-source)


## RTSP Cameras
EVAM supports RTSP camera feed as input source. The [doc](./advanced-guide/detailed_usage/camera/rtsp.md) provides details on configuring pipelines with RTSP source and also provides more resources on RTSP protocol. 


## Using RTSP as a source

You can either start a RTSP server to feed video or you can use RTSP stream from a camera and accordingly update the `uri` key in `source` section of request. 

Here is a request to start default pallet defect detection pipeline using RTSP camera feed as a source.
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
