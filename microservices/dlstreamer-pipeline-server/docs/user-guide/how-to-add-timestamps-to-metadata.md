# How to add system timestamps to metadata

This tutorial will help you add timestamp to metadata of each frame. This tutorial shows how to use the GST element 'timecodestamper' that adds timestamps to frames.

## Steps 
1. Update default config.json present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/config.json` with below configurations. 

* Update "pipeline" variable as follows -
```sh
"pipeline": "{auto_source} name=source  ! decodebin ! timecodestamper set=always ! videoconvert ! gvadetect name=detection ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true timestamp-utc=true name=metaconvert ! jpegenc ! appsink name=destination",

```

`NOTE` Make sure that proprety `set` of `timecodestamper` is set to `always`. `timecodestamper` element follows SMPTE format of storing data (hours:minutes:seconds:frames). 

`set` property can have anyone of the 3 values shown below
| Value  | Description |
| ------------- |:-------------:|
| never | Never set timecodes |
| keep | Keep upstream timecodes and only set if no upstream timecode |
| always | Always set timecode and remove upstream timecode |

`NOTE` While adding `timecodestamper` make sure to add property `timestamp-utc=true` to `gvametaconvert`. This ensures that SMPTE format is converted to UTC time format while instering into frame metadata.

* Add below mqtt config under "pipelines" section. 
```json
"mqtt_publisher":{
    "publish_frame": false,
    "topic": "pallet_defect_detection"
},
```

Your default config.json would look like this after above modifications - 
```json
{
    "config": {
        "pipelines": [
            {
                "name": "pallet_defect_detection",
                "source": "gstreamer",
                "queue_maxsize": 50,
                "pipeline": "{auto_source} name=source  ! decodebin ! timecodestamper set=always ! videoconvert ! gvadetect name=detection ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true timestamp-utc=true name=metaconvert ! jpegenc ! appsink name=destination",
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
                "mqtt_publisher":{
                    "publish_frame": false,
                    "topic": "pallet_defect_detection"
                },
                "auto_start": false
            }
        ]
    }
}
```

Ensure that the changes made to the config.json are reflected in the container by volume mounting it as menioned in this -[tutorial](../../../how-to-change-dlstreamer-pipeline.md#how-to-change-deep-learning-streamer-pipeline)

2. Update environment variables file present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` with below mentioned variables. Please add corresponding IP address in place of `<MQTT_BROKER_IP_ADDRESS>` below -
```sh
MQTT_HOST=<MQTT_BROKER_IP_ADDRESS>
MQTT_PORT=1883
```

3. Start the DLStreamer pipeline server
```sh
cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/    
docker compose up
```

4. Open another terminal and run the following command to sgtart the MQTT subscriber. 
```sh
docker run -d --name=mqtt_broker -p 8883:8883 -v $PWD/utils/mosquitto:/mosquitto/config eclipse-mosquitto
```

For more details on subscribing and running MQTT please refer to this [document](./advanced-guide/detailed_usage/publisher/eis_mqtt_publish_doc.md)

`NOTE` You should be able to see the metadata output in MQTT subscriber only after you run the curl command mentioned in step 5 below

5. Open another terminal and hit the following curl command to start the pipeline
```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
                "source": {
                    "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
                    "type": "uri"
                },
                "destination": {
                    "metadata": {
                        "type": "mqtt",
                        "publish_frame":false,
                        "topic": "pallet_defect_detection"
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

6. Your terminal with MQTT subscriber should now show the metadata output of each frame. You should be able to see an attribute called `system_timestamp` in the metadata of each frame. Sample output of a metadata from one frame shown below - 

```json
{"metadata": {"height": 480, "width": 640, "channels": 3, "caps": "video/x-raw, format=(string)NV12, width=(int)640, height=(int)480, interlace-mode=(string)progressive, multiview-mode=(string)mono, multiview-flags=(GstVideoMultiviewFlagsSet)0:ffffffff:/right-view-first/left-flipped/left-flopped/right-flipped/right-flopped/half-aspect/mixed-mono, pixel-aspect-ratio=(fraction)1/1, colorimetry=(string)2:4:16:3, framerate=(fraction)30/1", "img_format": "NV12", "img_handle": "M5FUMHIENZ", "objects": [{"detection": {"bounding_box": {"x_max": 0.9976633191108704, "x_min": 0.6692856550216675, "y_max": 0.5851964155832926, "y_min": 0.05542623996734619}, "confidence": 0.9157595038414001, "label": "box", "label_id": 0}, "h": 254, "region_id": 262, "roi_type": "box", "w": 210, "x": 428, "y": 27}, {"detection": {"bounding_box": {"x_max": 0.8332022428512573, "x_min": 0.7229064106941223, "y_max": 0.29518139362335205, "y_min": 0.21405665079752603}, "confidence": 0.8785356879234314, "label": "shipping_label", "label_id": 1}, "h": 39, "region_id": 263, "roi_type": "shipping_label", "w": 71, "x": 463, "y": 103}], "resolution": {"height": 480, "width": 640}, "system_timestamp": "2025-06-01T21:58:10.563Z", "tags": {}, "timestamp": 1733333333, "gva_meta": [{"x": 428, "y": 27, "height": 254, "width": 210, "object_id": null, "tensor": [{"name": "detection", "confidence": 0.9157595038414001, "label_id": 0, "label": "box"}]}, {"x": 463, "y": 103, "height": 39, "width": 71, "object_id": null, "tensor": [{"name": "detection", "confidence": 0.8785356879234314, "label_id": 1, "label": "shipping_label"}]}], "pipeline": {"name": "user_defined_pipelines", "version": "pallet_defect_detection", "instance_id": "80be9fda3f3311f0a6780242c0a85003", "status": {"avg_fps": 28.40975003297246, "avg_pipeline_latency": null, "elapsed_time": 1.8655478954315186, "id": "80be9fda3f3311f0a6780242c0a85003", "message": "", "start_time": 1748815089.0172741, "state": "RUNNING"}}, "frame_id": 52, "time": 1748815090882860032}, "blob": ""}
```