---
name: dlsps-user
description: >
  Deploy and operate the DL Streamer Pipeline Server microservice for real-time
  video analytics. Use this skill whenever a user wants to: start or stop a
  video analytics pipeline; run object detection, classification, or tracking
  on a video stream; configure GPU or NPU hardware acceleration for inference;
  stream processed video via RTSP or WebRTC; publish inference metadata over
  MQTT, OPC UA, InfluxDB, S3, or ROS2; deploy DL Streamer Pipeline Server via
  Docker Compose or Helm; write a custom GStreamer pipeline config; use the
  REST API to manage pipeline instances; troubleshoot pipeline errors or GPU
  access issues. Also trigger on phrases like "video analytics pipeline",
  "GStreamer inference", "DL Streamer", "DLSPS", "object detection on video",
  "RTSP streaming", "pipeline server".
argument-hint: >
  Describe your video analytics task (e.g. "run object detection on an RTSP
  camera stream using GPU and publish results to MQTT")
---

# DL Streamer Pipeline Server Agent

Set up and operate the DL Streamer Pipeline Server microservice for real-time
video analytics — from starting the container through pipeline management via
the REST API.

> **Preview:** This skill is in preview — share feedback to help improve it.

## When to Use

- User wants to run object detection or other inference on video streams
- User needs to start/stop/monitor video analytics pipelines via REST API
- User wants to configure GPU or NPU hardware acceleration
- User needs RTSP or WebRTC frame streaming output
- User wants to publish inference metadata to MQTT, OPC UA, S3, InfluxDB, or ROS2
- User is deploying DL Streamer Pipeline Server via Docker Compose or Helm
- User wants to write or modify a GStreamer pipeline config (config.json)
- User needs to run UDF (User Defined Function) pipelines
- User is troubleshooting pipeline failures, GPU access, or RTSP issues

## Architecture at a Glance

```
REST API (port 8080, OpenAPI 3.0 / Connexion)
    │
    ▼
Pipeline Manager (lifecycle: start / stop / status)
    │
    ▼
GStreamer Engine + DL Streamer Plugins
    │
    ├── Decode: CPU or GPU (decodebin3) │ GPU (vah264dec) │ CPU (avdec_h264)
    ├── Inference: gvadetect / gvaclassify (CPU, GPU, NPU)
    └── Publish: MQTT │ OPC UA │ S3 │ InfluxDB │ ROS2 │ File
    │
    ▼
Output: RTSP stream │ WebRTC stream │ metadata files
```

## REST API Quick Reference

**Base URL:** `http://localhost:8080`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/pipelines` | List available pipeline definitions |
| GET | `/pipelines/{name}/{version}` | Get a pipeline description |
| POST | `/pipelines/{name}/{version}` | **Start a new pipeline instance** |
| DELETE | `/pipelines/{instance_id}` | **Stop a running pipeline** |
| GET | `/pipelines/status` | Get status of all running pipelines |
| GET | `/pipelines/{instance_id}/status` | Get status of a specific instance |
| GET | `/models` | List available models |

### Request Body (POST — start pipeline)

```json
{
  "source": {
    "uri": "file:///path/to/video.avi",
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
      "path": "my-stream-name"
    }
  },
  "parameters": {
    "detection-properties": {
      "model": "/path/to/model.xml",
      "device": "CPU"
    }
  }
}
```

**Response:** Pipeline instance ID string, e.g. `"a6d67224eacc11ec9f360242c0a86003"`

### Metadata Destination Types

| `type` value | Description | Extra fields |
|--------------|-------------|--------------|
| `file` | Write JSON-lines to a file | `path`, `format` |
| `mqtt` | Publish to MQTT broker | `topic`, `publish_frame` (bool) |
| `opcua` | Publish via OPC UA | server configured by env vars |
| `s3` | Write to S3/MinIO | configured by env vars |
| `influxdb` | Write to InfluxDB | configured by env vars |

### Frame Destination Types

| `type` value | Description | Access URL |
|--------------|-------------|------------|
| `rtsp` | RTSP stream | `rtsp://<host>:8554/<path>` |
| `webrtc` | WebRTC stream | `http://<host>:8889` |

## Pipeline Configuration Format

Pipeline definitions live in a `config.json` mounted into the container:

```json
{
  "config": {
    "pipelines": [
      {
        "name": "my_pipeline",
        "source": "gstreamer",
        "queue_maxsize": 50,
        "pipeline": "{auto_source} ! decodebin3 ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
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

### Key GStreamer Elements

| Element | Purpose |
|---------|---------|
| `{auto_source}` | Auto-detect source (file, RTSP, camera) |
| `decodebin3` | System available decoder (CPU/GPU) |
| `vah264dec` | GPU VA-API H.264 decode |
| `vapostproc` | GPU VA-API post-processing |
| `gvadetect` | Object detection inference |
| `gvaclassify` | Classification inference |
| `gvametaconvert` | Convert inference results to metadata |
| `gvametapublish` | Publish metadata to destination |
| `udfloader` | Load Python User Defined Functions |
| `appsink` | Application sink (required) |

## Common Mistakes to Avoid

| Mistake | Correct |
|---------|---------|
| Using RTSP/MQTT with GPU pipeline without buffer conversion | Add `vapostproc ! video/x-raw` before `appsink` |
| RTSP streaming with UDF loader (RGB/BGR format) | Add `videoconvert ! video/x-raw, format=(string)NV12` before `appsink` |
| Forgetting `RENDER_GID` for GPU/NPU | Export `RENDER_GID=$(stat -c "%g" /dev/dri/render* \| head -1)` before compose |
| Using wrong port | REST API is on port **8080**, RTSP on **8554** |
| Not volume-mounting custom config | Mount via `-v ../configs/my_config/config.json:/home/pipeline-server/config.json` |
| Assuming NPU requires different container | Same container — set `device=NPU` |

---

## Example Scenarios

Read the matching example file — it contains the exact compact response format to follow:

| File | Covers |
|------|--------|
| [examples/detect-on-video-file.md](./examples/detect-on-video-file.md) | Run object detection on a local video file with CPU, stream results via RTSP |
| [examples/gpu-inference-mqtt.md](./examples/gpu-inference-mqtt.md) | GPU-accelerated inference with MQTT metadata publishing |

---

## Procedure

### Response Rules

- **Keep responses VERY short.** No verbose explanations. Use bold labels + inline code.
- **Always include the full pipeline lifecycle** in a single compact response: start service → launch pipeline (showing device + RTSP path in JSON) → RTSP URL → status check → stop command.
- Never omit the status-check or delete steps.
- Prefer single-line JSON in curl bodies. Omit optional fields (metadata destination) unless the user asks.
- Target under 600 characters total in your response.

### Execution Overview

1. Gather requirements from user prompt (source, device, output type)
2. Start the service (`cd .../docker && docker compose up`)
3. POST to `/pipelines/{name}/{version}` with source + destination + parameters
4. Show RTSP URL, status-check command, and stop command

**GPU/NPU rules:**
- GPU: `vah264dec`, `vapostproc`, `device=GPU`, `pre-process-backend=va-surface-sharing`
- NPU: `device=NPU`
- RTSP/MQTT with GPU: add `vapostproc ! video/x-raw` before `appsink`

Read reference files only when needed for advanced configuration details:
- [service-setup.md](./references/service-setup.md) — Docker Compose, env vars, ports
- [api-and-pipelines.md](./references/api-and-pipelines.md) — Full API details, pipeline configs
- [troubleshooting.md](./references/troubleshooting.md) — GPU/NPU issues, RTSP failures

---

**Every final answer must include: startup command, the curl POST with device and frame destination,
the RTSP URL (`rtsp://host:8554/stream-name`), a status-check command (`GET /pipelines/status`),
and a stop command (`DELETE /pipelines/{instance_id}`).** Keep responses compact — use single-line
JSON in curl commands when the body is short.
