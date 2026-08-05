# API & Pipeline Configuration Reference

This document covers the pipeline configuration schema and GStreamer element reference.
For REST API details, refer to the existing documentation.

---

## REST API

For full REST API endpoint descriptions, request/response formats, and usage examples, see:

- `docs/user-guide/api-reference.md`
- `docs/user-guide/advanced-guide/detailed_usage/rest_api/restapi_reference_guide.md`
- `docs/user-guide/advanced-guide/detailed_usage/rest_api/customizing_pipeline_requests.md`

---

## Pipeline Configuration

For pipeline definition schema (`config.json`) and how to define/customize pipelines, see:

- `docs/user-guide/advanced-guide/detailed_usage/rest_api/defining_pipelines.md`
- `docs/user-guide/advanced-guide/detailed_usage/configuration/dlstreamer-ps-config.md`
- `docs/user-guide/how-to-guides/launch-configurable-pipelines.md`
- `docs/user-guide/how-to-guides/change-dlstreamer-pipeline.md`

---

## GStreamer Pipeline Element Reference

### Source

| Element | Usage |
|---------|-------|
| `{auto_source}` | Automatic source selection based on REST request |

### Decode

| Element | Device | Description |
|---------|--------|-------------|
| `decodebin3` | CPU or GPU | Auto-select CPU or GPU decoder |
| `avdec_h264` | CPU | CPU H.264 software decode |
| `jpegdec` |	CPU	| CPU JPEG software decode |
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

### UDF Pipeline

```
{auto_source} ! decodebin3 ! videoconvert ! video/x-raw,format=RGB ! udfloader name=udfloader ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! videoconvert ! video/x-raw, format=(string)NV12 ! appsink name=appsink
```

> **Note:** UDF pipelines with RGB/BGR output need `videoconvert ! video/x-raw, format=(string)NV12`
> before `appsink` for RTSP compatibility.