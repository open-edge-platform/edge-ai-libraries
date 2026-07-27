# API & Pipeline Configuration Reference

This document covers the REST API endpoints, request/response formats,
pipeline configuration schema, and GStreamer element reference.

---

## REST API Endpoints

**Base URL:** `http://localhost:8080`

### List Pipelines

```
GET /pipelines
```

Returns a JSON array of available pipeline definitions.

### Get Pipeline Description

```
GET /pipelines/{name}/{version}
```

Returns the description and parameters of a specific pipeline.

### Start a Pipeline Instance

```
POST /pipelines/{name}/{version}
Content-Type: application/json
```

**Request body:**

```json
{
  "source": {
    "uri": "<video-source-uri>",
    "type": "uri"
  },
  "destination": {
    "metadata": {
      "type": "<file|mqtt|opcua|s3|influxdb>",
      "path": "/tmp/results.jsonl",
      "format": "json-lines"
    },
    "frame": {
      "type": "<rtsp|webrtc>",
      "path": "<stream-name>"
    }
  },
  "parameters": {
    "<parameter-group>": {
      "model": "<path-to-model.xml>",
      "device": "<CPU|GPU|NPU>"
    }
  },
  "sync": false
}
```

**Response:** Pipeline instance ID string, e.g. `"a6d67224eacc11ec9f360242c0a86003"`

#### Source Types

| `type` | `uri` format | Notes |
|--------|-------------|-------|
| `uri` | `file:///path/to/video.avi` | Local file inside container |
| `uri` | `rtsp://<ip>:<port>/<path>` | RTSP camera stream |

#### Metadata Destination Options

| `type` | Required fields | Env vars needed |
|--------|----------------|-----------------|
| `file` | `path`, `format` (`json-lines`) | — |
| `mqtt` | `topic`, optionally `publish_frame` (bool) | `MQTT_HOST`, `MQTT_PORT` |
| `opcua` | — | `OPCUA_SERVER_IP`, `OPCUA_SERVER_PORT`, `OPCUA_SERVER_USERNAME`, `OPCUA_SERVER_PASSWORD` |
| `s3` | — | `S3_STORAGE_HOST`, `S3_STORAGE_PORT`, `S3_STORAGE_USER`, `S3_STORAGE_PASS` |
| `influxdb` | — | `INFLUXDB_HOST`, `INFLUXDB_PORT`, `INFLUXDB_USERNAME`, `INFLUXDB_PASS` |

#### Frame Destination Options

| `type` | Required fields | Access |
|--------|----------------|--------|
| `rtsp` | `path` (stream name) | `rtsp://<host>:8554/<path>` |
| `webrtc` | `path` | `http://<host>:8889` (requires MediaMTX) |

### Stop a Pipeline

```
DELETE /pipelines/{instance_id}
```

### Get All Pipeline Status

```
GET /pipelines/status
```

Returns JSON array with status of all running/completed pipeline instances.

### Get Specific Pipeline Status

```
GET /pipelines/{instance_id}/status
```

Returns JSON object with pipeline state (e.g. `RUNNING`, `COMPLETED`, `ERROR`).

### List Models

```
GET /models
```

Returns available models known to the server.

---

## Pipeline Configuration Schema (config.json)

Pipelines are defined in a `config.json` file mounted into the container at
`/home/pipeline-server/config.json`.

### Full Schema

```json
{
  "config": {
    "pipelines": [
      {
        "name": "<pipeline-name>",
        "source": "gstreamer",
        "queue_maxsize": 50,
        "pipeline": "<gstreamer-pipeline-string>",
        "parameters": {
          "type": "object",
          "properties": {
            "<param-group-name>": {
              "element": {
                "name": "<gst-element-name>",
                "format": "element-properties"
              }
            }
          }
        },
        "auto_start": false,
        "mqtt_publisher": {
          "publish_frame": true,
          "topic": "<mqtt-topic>"
        }
      }
    ]
  }
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Pipeline name used in REST URL path |
| `source` | string | Yes | Always `"gstreamer"` |
| `queue_maxsize` | int | No | Max GStreamer queue size (default: 50) |
| `pipeline` | string | Yes | GStreamer pipeline string |
| `parameters` | object | No | Parameter groups exposed via REST API |
| `auto_start` | bool | No | Auto-start on container boot (default: false) |
| `mqtt_publisher` | object | No | MQTT publishing config for this pipeline |

---

## GStreamer Pipeline Element Reference

### Source

| Element | Usage |
|---------|-------|
| `{auto_source}` | Automatic source selection based on REST request |

### Decode

| Element | Device | Description |
|---------|--------|-------------|
| `decodebin3` | CPU | Auto-select CPU decoder |
| `vah264dec`  | GPU | VA-API H.264 hardware decode |
| `vajpegdec`  | GPU | VA-API JPEG hardware decode |

### Processing

| Element | Description |
|---------|-------------|
| `videoconvert` | Color space conversion (CPU) |
| `vapostproc` | VA-API post-processing (GPU) |
| `video/x-raw(memory:VAMemory)` | Zero-copy GPU buffer capability |
| `video/x-raw` | Force CPU buffer (needed before appsink for RTSP/MQTT with GPU) |

### Inference (DL Streamer)

| Element | Description | Key Properties |
|---------|-------------|----------------|
| `gvadetect` | Object detection | `name`, `model-instance-id`, `device` (CPU/GPU/NPU), `pre-process-backend` |
| `gvaclassify` | Classification | Same as gvadetect |
| `gvafpscounter` | FPS measurement | — |
| `gvametaconvert` | Convert to metadata | `add-empty-results=true` |
| `gvametapublish` | Publish metadata | `name=destination` |

### UDF

| Element | Description |
|---------|-------------|
| `udfloader` | Load Python User Defined Functions |

### Sink

| Element | Description |
|---------|-------------|
| `appsink` | Application sink (always `name=appsink`) |

---

## Sample Pipeline Strings

### CPU Decode + CPU Inference

```
{auto_source} ! parsebin ! avdec_h264 ! videoconvert ! video/x-raw ! queue ! gvadetect name=detection model-instance-id=inst0 device=CPU pre-process-backend=opencv ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink
```

### GPU Decode + GPU Inference

```
{auto_source} ! parsebin ! vah264dec ! vapostproc ! video/x-raw(memory:VAMemory) ! queue ! gvadetect name=detection model-instance-id=inst0 device=GPU pre-process-backend=va-surface-sharing ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! queue ! gvafpscounter ! appsink name=appsink
```

> **Important:** If using RTSP or MQTT with GPU pipeline, add `vapostproc ! video/x-raw`
> before `appsink` to convert from GPU memory to CPU buffer.

### GPU Decode + GPU Inference + RTSP Output

```
{auto_source} ! parsebin ! vah264dec ! vapostproc ! video/x-raw(memory:VAMemory) ! gvadetect name=detection model-instance-id=inst0 device=GPU pre-process-backend=va-surface-sharing ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! vapostproc ! video/x-raw ! appsink name=appsink
```
