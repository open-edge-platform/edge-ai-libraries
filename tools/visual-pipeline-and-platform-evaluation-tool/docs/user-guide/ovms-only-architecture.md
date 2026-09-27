# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Vippet and OVMS: Current Streaming POC

This document describes the current file-to-file proof of concept. It uses the `publicDetection` graph and one KServe gRPC stream. It does not use the legacy GETi API at `/v3/{graph_name}` or a GStreamer pipeline.

## 1. Vippet Remains the Product and Orchestration Layer

- FastAPI exposes the API and supports the UI, pipeline definitions, performance tests, file uploads, and job history.
- The UI lets users select a pipeline, video source, number of in-flight requests, and test duration.
- `PipelineManager` still loads YAML files, but their role changes: YAML describes a Python processing flow rather than a textual GStreamer pipeline.
- The `/ovms-poc/run` endpoint starts `ovms_poc_runner.py` with configuration written for the specific job.

Current flow:

```text
Vippet API/UI -> Python media runner -> OpenCV / FFmpeg / PyAV
              -> OVMS KServe gRPC stream -> post-processing -> metadata / output / metrics
```

## 2. Reference Pipeline Definition Format

- The system moves away from `pipeline_description: "filesrc ... ! decodebin3 ! gvapython ..."` and toward structured data.
- A pipeline describes its input, decoder, OVMS models, stage ordering, post-processing, output, and metrics.

```yaml
name: Public Object Detection via OVMS Streaming
type: vision
runtime: python-ovms

input:
  type: video-file
  path: /videos/input/auto/obj_classification.mp4

execution:
  max_parallel_requests: 2
  queue_size: 8
  request_timeout_s: 30

stages:
  - name: detection
    type: ovms-kserve-grpc-stream
    model: publicDetection
    endpoint: ovms:9000
    max_width: 1920
    max_height: 1080

output:
  video_path: /videos/output/public-object-detection-output.mp4
  metadata_path: /metadata/public-object-detection-output.jsonl
  overlay: true

metrics:
  enabled: true
```

- This YAML is a reference POC description. The current `/ovms-poc` flow starts the runner directly and is not executed by `PipelineManager`.

## 3. Python Runner

- `vippet/ovms_poc_runner.py` receives job configuration and the `job_id`.
- It decodes frames, keeps a bounded number of requests in flight, and writes the output video and JSONL metadata.
- Status, FPS, latency, and artifact paths are written to job files and exposed through the API.

## 4. Source Decoding Without GStreamer

- The POC uses `cv2.VideoCapture` and `cv2.VideoWriter`; FFmpeg converts the final MP4 to H.264 with `yuv420p`.
- Supported inputs include local `mp4`, `mkv`, `mov`, and `avi` files, RTSP when OpenCV has an FFmpeg backend, and a USB camera such as `cv2.VideoCapture(0)`.
- A more robust production deployment should use PyAV, the FFmpeg bindings. It provides explicit stream and codec detection, better RTSP handling, timestamp control, and easier remuxing or re-encoding.
- FFmpeg or PyAV replaces decoding, pixel conversion, and encoding, not OVMS.

## 5. Frame Ordering and Concurrent Requests

- `max_parallel_requests` is a pipeline parameter rather than a code constant.
- Each frame receives a monotonic identifier and timestamp.
- The runner starts one `tritonclient.grpc.InferenceServerClient.start_stream()` call and asynchronously sends several requests on that stream.
- Results can arrive out of order, but video and metadata writes preserve source-frame order.
- The processing model is:
  1. Read a frame.
  2. Prepare an OVMS request.
  3. Add the request to a bounded queue.
  4. When the queue reaches its limit, receive a completed request.
  5. Apply the result to its corresponding frame.
  6. Write the frame and metadata.
- `pending_frames` and `completed_frames` in `ovms_poc_runner.py` preserve source-frame order despite out-of-order responses.

## 6. Python Pre-processing

- Pre-processing must not be hidden in `gvapython` or the DLStreamer `model_proc` configuration.
- Each stage explicitly defines its expected color space (BGR or RGB), input size, resize method (stretch, letterbox, or crop), normalization, data type (`uint8`, `float32`, or `float16`), and tensor layout (`HWC` or `NCHW`).
- The client downscales frames while preserving aspect ratio, creates a contiguous HWC `UINT8` NumPy tensor, and sends it through `tritonclient.grpc`.
- OVMS receives individual unencoded frames; it does not receive the entire MP4 as one request.

## 7. OVMS Client Layer

- The client can later be extracted from the runner, for example:

```text
vippet/ovms/
  client.py
  models.py
  health.py
  stages.py
```

- The client uses KServe gRPC and sends the monotonic `OVMS_MP_TIMESTAMP` parameter for every frame.
- `max_parallel_requests` limits client-side in-flight requests; it does not set OVMS `NUM_STREAMS` or `nireq`.
- REST `GET /v2/health/ready` is used only to verify OVMS readiness before a job starts.

## 8. Model-specific Post-processing

- The `publicDetection` graph currently returns only `annotated_image`. Detection and label rendering run in the MediaPipe graph, but structured bounding boxes are not yet serialized in the response.
- Future adapters can convert model responses to a common Vippet data model:

```python
Detection(
    label="person",
    confidence=0.94,
    x=120,
    y=85,
    width=240,
    height=510,
)
```

- The common format can support bounding boxes, labels and confidence, segmentation masks, keypoints, tracking IDs, full-frame or ROI classification, and custom attributes.

## 9. Multi-stage Pipelines Without GVA Metadata

- A future `detection -> classification` pipeline can perform the following flow:
  1. Decode a frame.
  2. Send the full frame to an OVMS detection model.
  3. Run NMS and determine ROIs.
  4. Crop ROIs for matching classes.
  5. Send ROIs concurrently to an OVMS classification model.
  6. Attach classification results to detections.
  7. Render or persist the result.
- This replaces a flow such as `gvapython module=ovms_detection.py ! gvapython module=ovms_classification.py`.
- The stage dependency should be described in YAML, for example `input: detections.rois`, rather than encoded in GStreamer element order.

## 10. Overlay and Video Output

- The MediaPipe graph renders detection boxes and labels on the original image before returning `annotated_image`.
- The runner scales the returned frame to source resolution, writes it through `cv2.VideoWriter`, and then publishes an H.264 MP4 through FFmpeg.

## 11. Metadata Replaces `gvametaconvert` and `gvametapublish`

- A JSON Lines record should be written for every frame, for example:

```json
{
  "job_id": "...",
  "frame_id": 512,
  "timestamp_ms": 17066.7,
  "source": "/videos/input/auto/obj_classification.mp4",
  "inference_ms": 23.2,
  "detections": [
    {
      "label": "bottle",
      "confidence": 0.94,
      "bbox": {"x": 120, "y": 85, "width": 240, "height": 510}
    }
  ]
}
```

- The file is written to the `/metadata` volume.
- The Vippet API returns the URL or path for the metadata and output video.
- The metadata schema should be stabilized and covered by contract tests because it replaces the implicit DLStreamer format.

## 12. Metrics Replace `gvafpscounter` and the Latency Tracer

- The system should measure decoding FPS, end-to-end FPS, mean, median, and p95 OVMS request time, pre-processing, post-processing, rendering and write time, timeout, error, and skipped-frame counts, as well as the current queue length.
- The POC records client-observed `mean_ovms_inference_ms`, `p95_ovms_inference_ms`, and `end_to_end_fps`.
- Each completed job summary also records backend metrics from OVMS's `ovms_inference_time_us` histogram: `ovms_model_name`, `ovms_inference_count`, `ovms_inference_time_us`, `ovms_mean_inference_ms`, and `ovms_fps`.
- With $N$ concurrent requests, $1/t$ does not represent total throughput. Measure:

$$
\text{OVMS throughput} = \frac{\text{completed inference requests}}{\text{measurement interval}}
$$

- The runner can publish statistics to `metrics-manager` if it remains in the architecture, or Vippet can persist them locally and expose them through the API.

## 13. Separate Job Lifecycle

- `PipelineRunner` should not parse GStreamer stdout.
- A future runner can report structured JSON events through stdout, a status file, or IPC:

```json
{"event":"started","job_id":"..."}
{"event":"progress","frames":300,"fps":28.4}
{"event":"completed","frames":900,"output":"/videos/output/result.mp4"}
```

- Vippet updates job status from these messages.
- Stopping a test sends `SIGTERM`; the runner stops reading new frames, drains or cancels submitted requests after a timeout, closes the writer, writes partial metadata, and marks the job as cancelled.

## 14. Model Management Separate from `model-download`

- In a simple deployment, models are part of the OVMS repository:

```text
shared/ovms/model_repository/
  geti/6/
  yolo11n-int8/1/
  efficientnet-b0-int8/1/
```

- `shared/ovms/config.json` defines the models and graphs loaded at startup.
- Vippet can read an OVMS manifest, but should not assume a model exists in `/models/output` or use DLStreamer model-proc configuration.
- Vippet checks `/v2/health/ready` before starting a job.
- Dynamic model addition requires a separate service that validates the model, stores it in the OVMS repository, updates configuration, safely reloads OVMS, and verifies model readiness.
- The first version should use a static model repository.

## 15. Minimal Compose Services

- The minimum stack without UI, RTSP streaming, ONVIF cameras, or dynamic model downloads is:

```text
vippet-api
ovms
```

- `vippet-ui` can be added optionally.
- File-to-file mode does not need DLStreamer, GStreamer, `mediamtx`, `onvif-discovery`, `model-download`, or `metrics-manager`.
- Vippet must remove or conditionally apply `depends_on` for `mediamtx`, `model-download`, and `onvif-discovery`.

## 16. New Vippet Image

- The `vippet/Dockerfile` base image should change from `intel/dlstreamer:...` to an Ubuntu-based Python or OpenVINO Runtime image.
- Install only Python, OpenCV with FFmpeg or PyAV, `requests` or `httpx`, `tritonclient[grpc]` when V2 gRPC is used, NumPy, and the current backend's FastAPI dependencies.
- `openvino` is optional; it is needed only if Vippet validates models locally or performs conversions.
- Remove `GST_PLUGIN_PATH`, `DLSTREAMER_MODEL_PROC_DIR`, `DLSTREAMER_LABELS_DIR`, `OMZ_VIRTUAL_ENV`, `requirements-omz.txt` when OMZ downloads or conversion are not needed, and code using `gvapython`, `gva*`, and `gst_runner.py`.

## 17. Implementation Order

1. Maintain the current `ovms_poc_runner.py` and public graph as a verifiable POC.
2. Add structured detections to the graph response when the UI or API needs them.
3. Only then extend the mechanism with YAML runtime support, RTSP, cameras, and dynamic model management.

## 18. Completion Criteria

- `docker compose up ovms vippet` starts OVMS and Vippet with the active public graph.
- Vippet processes a local MP4 from input to output.
- Frames reach OVMS through one KServe gRPC stream.
- The resulting MP4 includes a prediction overlay.
- JSONL includes the frame identifier, timestamp, round-trip time, response timestamp, and output shape.
- The UI and API expose FPS, mean and p95 inference time, and job artifacts.
- Unavailable OVMS or a missing model blocks job startup with a clear message without starting a partial pipeline.