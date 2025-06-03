# Customizing Pipeline Requests
| [Request Format](#request-format) | [Source](#source) | [Destination](#metadata-destination) | [Parameters](#parameters) | [Tags](#tags) |

Pipeline requests are initiated to exercise the Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server) REST API. Each pipeline in the DL Streamer Pipeline Server has a specific endpoint. A pipeline can be started by issuing a `POST` request and a running pipeline can be stopped using a `DELETE` request. The `source` and `destination` elements of Pipeline Server [pipeline templates](defining_pipelines.md#pipeline-templates) are configured and constructed based on the `source` and `destination` from the incoming requests.

## Request Format

Pipeline requests sent to Pipeline Server REST API are JSON documents that have the following attributes:

|Attribute | Description |
|---------|-----|
|`source`| Required attribute specifying the video source that needs to be analyzed. It consists of : <br>    `uri` : the uri of the video source that needs to be analyzed <br>    `type` : is the value `uri` |
|`destination`| Optional attribute specifying the output to which analysis results need to be sent/saved. It consists of `metadata` and `frame`|
|`parameters`| Optional attribute specifying pipeline parameters that can be customized when the pipeline is launched.|
|`tags`| Optional attribute specifying a JSON object of additional properties that will be added to each frame's metadata.|

### Example Request
Below is a sample request using curl to start an `user_defined_pipelines/pallet_defect_detection` pipeline that analyzes the video warehouse.avi and sends its results to `/tmp/results.jsonl`.

> Note: Files specified as a source or destination need to be accessible from within the DL Streamer Pipeline Server container. Local files and directories can be volume mounted using standard docker volume mounted options in docker compose file i.e [WORKDIR/docker/docker-compose.yml]. 

```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
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
```
1d51bc30fa4f11ef819f0242ac160004
```

The number returned on the console is the pipeline instance id (e.g. `1d51bc30fa4f11ef819f0242ac160004`).
As the video is being analyzed and as objects are detected, results are added to the `destination` file which can be viewed using:

```bash
tail -f /tmp/results.jsonl
```
```

{"objects":[{"detection":{"bounding_box":{"x_max":0.22907545935595408,"x_min":0.0006581820198334754,"y_max":0.6680994778871536,"y_min":0.19497551023960114},"confidence":0.8847041130065918,"label":"box","label_id":0},"h":227,"region_id":2201,"roi_type":"box","w":146,"x":0,"y":94}],"resolution":{"height":480,"width":640},"tags":{},"timestamp":39947419409}
{"objects":[{"detection":{"bounding_box":{"x_max":0.2249157302430831,"x_min":0.0006340466788969934,"y_max":0.6713097244501114,"y_min":0.19643743336200714},"confidence":0.8805060386657715,"label":"box","label_id":0},"h":228,"region_id":2202,"roi_type":"box","w":144,"x":0,"y":94}],"resolution":{"height":480,"width":640},"tags":{},"timestamp":39980820261}
<snip>
```

## Source
The `source` attribute specifies the video source that needs to be analyzed. It can be changed to use media from different sources.
Some of the common video sources are:

* File Source
* IP Camera (RTSP Source)
* Web Camera

> Note: See [Source Abstraction](./defining_pipelines.md#source-abstraction) to learn about GStreamer source elements set per request.

### File Source
The following example shows a media `source` from a video file in GitHub: 

```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
    "source": {
        "uri": "https://github.com/intel-iot-devkit/sample-videos/blob/master/person-bicycle-car-detection.mp4?raw=true",
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
A local file can also be used as a source. In the following example, `warehouse.avi` that has been copied to `/tmp` from `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/resources/videos/` is used as video source and Pipeline can be started with below curl request:

```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
    "source": {
        "uri": "file:///tmp/warehouse.avi",
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

### RTSP Source
RTSP streams originating from IP cameras, DVRs, or similar sources can be referenced using the `rtsp` URI scheme.

The request `source` object would be updated to:

```json
{
    "source": {
        "uri": "rtsp://<ip_address>:<port>/<server_url>",
        "type": "uri"
    }
}
```

#### RTSP Basic Authentication
Depending on the configuration of your media source, during development and troubleshooting you may issue Pipeline Server requests that include RTSP URIs formatted as `rtsp://<user>:<password>@<ip_address>:<port>/<server_url>` where `<user>` and `<password>` are authentication credentials needed to connect to the stream/device at `<ip_address>`.

> **Warning**: Keep in mind that basic authentication does not provide a secure method to access source inputs and to verify visual, metadata, and logged outputs. For this reason basic authentication is not recommended for production deployments, please use with caution.


## Setting source properties
For any of the sources mentioned above, it is possible to set properties on the source element via the request.

### Setting a property on source bin element
For example, to set property `buffer-size` on urisourcebin, source section can be set as follows:
```json
{
    "source": {
        "uri": "file:///tmp/warehouse.avi",
        "type": "uri",
        "properties": {
            "buffer-size": 4096
        }
    }
}
```

### Setting a property on underlying element
For example, if you'd like to set `ntp-sync` property of the `rtspsrc` element to synchronize timestamps across RTSP source(s).

> Note: This feature, enabled via GStreamer `source-setup` callback signal is only supported for `urisourcebin` element.

```json
{
    "source": {
        "uri": "rtsp://<ip_address>:<port>/<server_url>",
        "type": "uri",
        "properties": {
            "ntp-sync": true
        }
    }
}
```

## Metadata Destination
Pipelines can optionally be configured to output metadata to a specific destination.

For metadata, the destination type can be set to file, mqtt, or kafka as needed.


### File
The following are available properties:
- type : "file"
- path (required): Path to the file.
- format (optional): Format can be of the following types (default is json):
  - json-lines : Each line is a valid JSON.
  - json : Entire file is formatted as a JSON.

Below is an example for JSON format

```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results.jsonl",
            "format": "json"
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

### MQTT
The following are available properties:
- type : "mqtt"
- host (required) expects a format of host:port
- topic (required) MQTT topic on which broker messages are sent
- timeout (optional) Broker timeout
- mqtt-client-id (optional) Unique identifier for the MQTT client

Steps to run MQTT:
  1. Start the MQTT broker, here we use [Eclipse Mosquitto](https://hub.docker.com/_/eclipse-mosquitto/), an open source message broker.
  ```bash
  docker run --network=host eclipse-mosquitto:1.6
  ```
  2. Start the Pipeline Server with host network enabled
  ```bash
  docker/run.sh -v /tmp:/tmp --network host
  ```
  3. Send the REST request : Using the default 1883 MQTT port.
  ```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "<MQTT-HOST-IP>:1883",
            "topic": "pipeline-server",
            "mqtt-client-id": "gva-meta-publish"
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
  4. Connect to MQTT broker to view inference results
  ```bash
  docker run -it --network=host --entrypoint mosquitto_sub eclipse-mosquitto:1.6 --topic pipeline-server --id mosquitto-sub
  ```

  ```bash
{"objects":[{"detection":{"bounding_box":{"x_max":0.4873234033584595,"x_min":0.4171516001224518,"y_max":0.5046840906143188,"y_min":0.42876100540161133},"confidence":0.8322018384933472,"label":"defect","label_id":2},"h":36,"region_id":7649,"roi_type":"defect","w":45,"x":267,"y":206},{"detection":{"bounding_box":{"x_max":0.5919315814971924,"x_min":0.2966548502445221,"y_max":0.6308711767196655,"y_min":0.27925050258636475},"confidence":0.8213143348693848,"label":"box","label_id":0},"h":169,"region_id":7650,"roi_type":"box","w":189,"x":190,"y":134}],"resolution":{"height":480,"width":640},"tags":{},"timestamp":45458560046}
{"objects":[{"detection":{"bounding_box":{"x_max":0.5899640917778015,"x_min":0.29215648770332336,"y_max":0.6300166249275208,"y_min":0.27991005778312683},"confidence":0.8384196162223816,"label":"box","label_id":0},"h":168,"region_id":7651,"roi_type":"box","w":191,"x":187,"y":134},{"detection":{"bounding_box":{"x_max":0.48560789227485657,"x_min":0.4089825749397278,"y_max":0.5054529309272766,"y_min":0.42728742957115173},"confidence":0.7293270230293274,"label":"defect","label_id":2},"h":38,"region_id":7652,"roi_type":"defect","w":49,"x":262,"y":205}],"resolution":{"height":480,"width":640},"tags":{},"timestamp":45491960898}
  ```
  5. In the MQTT broker terminal, you should see the connection from client with specified `mqtt-client-id`
  ```
  <snip>
  1632949258: New connection from 127.0.0.1 on port 1883.
  1632949258: New client connected from 127.0.0.1 as gva-meta-publish (p2, c1, k20).
  1632949271: New connection from 127.0.0.1 on port 1883.
  1632949271: New client connected from 127.0.0.1 as mosquitto-sub (p2, c1, k60).
  1632949274: Client gva-meta-publish disconnected.
  ```

## Frame Destination
`Frame` is another type of destination that sends frames with superimposed bounding boxes over either RTSP or WebRTC protocols.

### RTSP

Steps for visualizing output over RTSP assuming Pipeline Server and your VLC client are running on the same host.

1. Start a pipeline with  frame destination type set as `rtsp` and an endpoint path `pallet-defect-detection`.
```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "file",
            "format": "json-lines",
            "path": "/tmp/results.jsonl"
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
2. Use an RTSP client such as VLC to visualize the stream at address `rtsp://localhost:8554/pallet-defect-detection`.


The following parameters can be optionally used to customize the stream:
- path (required): custom string to uniquely identify the stream
- cache-length (default 30): number of frames to buffer in rtsp pipeline.
- encoding-quality (default 85): jpeg encoding quality (0 - 100). Lower values increase compression but sacrifice quality.
- sync-with-source: rate limit processing pipeline to encoded frame rate (e.g. 30 fps). Can be set to either `true` or `false`.
- sync-with-destination (default True): block processing pipeline if rtsp pipeline is blocked.

> **Note:** If the RTSP stream playback is choppy this may be due to
> network bandwidth. Decreasing the encoding-quality or increasing the
> cache-length can help.

### WebRTC

#### Request WebRTC Frame Output
1. To stream over WebRTC follow the pre-requisite steps for [WebRTC](../how-to-advanced/webrtc-frame-streaming.md) before sending the REST API request.

2. Start a pipeline to request frame destination type set as WebRTC and unique `peer-id` value set. For demonstration, peer-id is set as `pallet_defect_detection` in example request below.

```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "file",
            "format": "json-lines",
            "path": "/tmp/results.jsonl"
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "pallet_defect_detection"
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
3. Check that pipeline is running using [status request](../../detailed_usage/rest_api/restapi_reference_guide.md#get-pipelinesstatus) before trying to connect the WebRTC peer.
4. View the pipeline stream in your browser with url `http://<HOST_IP>:8889/pallet_defect_detection` where  `pallet_defect_detection` is the `peer-id` value which we sent in the request.


#### WebRTC Destination Parameters
Use the following parameters to customize the request:
- type : "webrtc"
- peer-id (required): custom string to uniquely identify the stream. May contain alphanumeric or underscore `_` characters only.
- bitrate (default 2048 kbps): The amount of data (in kb per second) used for encoding the stream, which affects the quality of streaming.
- cache-length (default 30): number of frames to buffer in WebRTC pipeline.
- sync-with-source: rate limit processing pipeline to encoded frame rate (e.g. 30 fps). Can be set to either `true` or `false`.
- sync-with-destination (default True): block processing pipeline if WebRTC pipeline is blocked.

> **Note:** If WebRTC stream playback is choppy this may be due to
> network bandwidth. Increasing the
> cache-length can help.


## Parameters
Pipeline parameters as specified in the pipeline definition file, can be set in the REST request.
For example, below is a the snippets from [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/config/default/config.json file:

```json
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
    }
}
```

Any or all of the parameters defined i.e detection-device, detection-model-instance-id, inference-interval and threshold can be set via the request.

```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
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

In the above example of REST request, the inferencing backend device is set to GPU. This would result in reduced use of HOST CPU which can be checked using system utilities like `top` or `htop`.

For more details on parameters, see [Pipeline Parameters](defining_pipelines.md#pipeline-parameters)

## Tags

Tags are pieces of information specified at the time of request, stored with frames metadata. In the example below, tags are used to describe the location and orientation of video input.

```bash
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H \
'Content-Type: application/json' -d \
'{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results.jsonl",
            "format": "json"
        }
    },
    "tags": {
        "camera_location": "conveyor_belt",
    },
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
}'
```

Inference results are updated with tags

```json
{
   "tags": {
      "camera_location": "conveyor_belt",
      "direction": "east"
  },
  "timestamp": 1500000000
}
```