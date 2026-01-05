# How to add system timestamps to metadata

This tutorial will help you add timestamp to metadata of each frame. This tutorial shows how to use the GST element 'timecodestamper' that adds timestamps to frames.

## Steps
1. Update default config.json present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/config.json` with below configurations.

* Update "pipeline" variable as follows -
```sh
"pipeline": "{auto_source} name=source  ! decodebin ! timecodestamper set=always ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
```

`NOTE` Make sure that proprety `set` of `timecodestamper` is set to `always`. `timecodestamper` element follows SMPTE format of storing data (hours:minutes:seconds:frames).

`set` property can have anyone of the 3 values shown below
| Value  | Description |
| ------------- |:-------------:|
| never | Never set timecodes |
| keep | Keep upstream timecodes and only set if no upstream timecode |
| always | Always set timecode and remove upstream timecode |

Ensure that the changes made to the config.json are reflected in the container by volume mounting it as mentioned in this [tutorial](./how-to-change-dlstreamer-pipeline.md)

2. Start the DL Streamer pipeline server
```sh
cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/
docker compose up
```

3. Open another terminal and run the following curl command to start the pipeline.
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

4. To view the metadata, open another terminal and run the following command
```sh
tail -f /tmp/results.jsonl
```

You should see an attribute called `system_timestamp` in the metadata of each frame. Sample output of a metadata from one frame shown below -
```json
{"objects":[{"detection":{"bounding_box":{"x_max":0.37195673026144505,"x_min":0.02789940871298313,"y_max":0.7120070457458496,"y_min":0.17735711733500162},"confidence":0.9217351078987122,"label":"box","label_id":0},"h":257,"region_id":2319,"roi_type":"box","w":220,"x":18,"y":85},{"detection":{"bounding_box":{"x_max":0.17977098003029823,"x_min":0.06219940260052681,"y_max":0.42195435365041095,"y_min":0.3419050375620524},"confidence":0.9094383120536804,"label":"shipping_label","label_id":1},"h":38,"region_id":2320,"roi_type":"shipping_label","w":75,"x":40,"y":164}],"resolution":{"height":480,"width":640},"system_timestamp":"2025-06-02T08:15:14.870:+0000","tags":{},"timestamp":7766666666}
```