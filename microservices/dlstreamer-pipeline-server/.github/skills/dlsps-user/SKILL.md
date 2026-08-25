---
name: dlsps-user
description: >
  Deploy and operate DL Streamer Pipeline Server — a microservice that wraps
  DL Streamer pipelines behind a REST API for containerized, no-code operation.
  Use this skill whenever a user wants to: deploy the pipeline server via
  Docker Compose or Helm; start, stop, or monitor pipeline instances through
  the REST API; configure pipeline definitions in config.json; publish inference
  metadata over MQTT, OPC UA, InfluxDB, S3, or ROS2; set up GPU/NPU device
  access for the container; troubleshoot service-level issues (container startup,
  REST errors, port conflicts). This skill is NOT for writing new DL Streamer
  applications or custom GStreamer code — use the dlstreamer-coding-agent skill
  for that. Trigger on phrases like "pipeline server", "DLSPS", "start pipeline
  via REST", "deploy video analytics microservice", "config.json pipeline
  definition".
---

# DL Streamer Pipeline Server Agent

Set up and operate the DL Streamer Pipeline Server microservice for real-time
video analytics — from starting the container through pipeline management via
the REST API.

> **Preview:** This skill is in preview — share feedback to help improve it.

## When to Use

- User wants to deploy the pipeline server container (Docker Compose or Helm)
- User needs to start/stop/monitor pipeline instances via the REST API
- User wants to configure pipeline definitions in `config.json`
- User needs to set up GPU/NPU device access for the container (`RENDER_GID`, device plugins)
- User wants to configure metadata publishing destinations (MQTT, OPC UA, S3, InfluxDB, ROS2)
- User is troubleshooting service-level issues (container startup, REST errors, port conflicts)

> **Not this skill:** If the user wants to *write new* DL Streamer applications,
> create custom GStreamer pipelines from scratch, or develop Python/C++ video analytics
> code, use the [`dlstreamer-coding-agent`](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent) skill instead.

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

### Key Pipeline Server Elements

| Element | Purpose |
|---------|---------|
| `{auto_source}` | Auto-detect source based on REST request |
| `udfloader` | Load Python User Defined Functions |
| `appsink` | Application sink (required, `name=appsink`) |

For DL Streamer inference, decode and metadata conversion and publishing elements see the [`dlstreamer-coding-agent`](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent) skill.

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
| [example-prompts/detect-on-video-file.md](./example-prompts/detect-on-video-file.md) | Run object detection on a local video file with CPU, stream results via RTSP |
| [example-prompts/gpu-inference-mqtt.md](./example-prompts/gpu-inference-mqtt.md) | GPU-accelerated inference with MQTT metadata publishing |

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
For GPU/NPU inference or decodeing devices see the [`dlstreamer-coding-agent`](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent) skill.
- RTSP/MQTT with GPU: add `vapostproc ! video/x-raw` before `appsink`

Read reference files only when needed for advanced configuration details:
- [service-setup.md](./references/service-setup.md) — Docker Compose, env vars, ports
- [api-and-pipelines.md](./references/api-and-pipelines.md) — Full API details, pipeline configs
- [troubleshooting.md](./references/troubleshooting.md) — GPU/NPU issues, RTSP failures

---

**Every final answer must include: startup command, the curl POST with device and frame destination,
the RTSP URL (`rtsp://host:8554/stream-name`), a status-check command (`GET /pipelines/status`),
and a stop command (HTTP `DELETE` on `/pipelines/<instance_id>`).** Keep responses compact — use single-line
JSON in curl commands when the body is short.
