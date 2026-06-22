# EVAM / DL Streamer Pipeline Server reference for VSS

This reference is grounded in the Video Search & Summarization sample application, not generic EVAM usage.

## Where the integration lives

| Concern | Repo path | Notes |
|---|---|---|
| Pipeline definitions | `video-ingestion/resources/conf/config.json` | Copied into the image as `/home/pipeline-server/config.json`. |
| Pipeline Server image | `video-ingestion/docker/Dockerfile` | `FROM intel/dlstreamer-pipeline-server:2026.1.0-ubuntu24-rc2`. |
| Python publisher used by `gvapython` | `video-ingestion/src/publish.py` | Copied to `/home/pipeline-server/gvapython/publisher/`. |
| EVAM request DTO and pipeline enum | `pipeline-manager/src/evam/models/evam.model.ts` | Defines `ChunkingRequestDTO`, `EVAMPipelines`. |
| EVAM HTTP client | `pipeline-manager/src/evam/services/evam.service.ts` | Builds POST URL/body and polls status. |
| RabbitMQ consumer | `pipeline-manager/src/evam/services/rabbitmq.service.ts` | Consumes MQTT-published chunk messages through AMQP. |
| Pipeline-manager EVAM config | `pipeline-manager/src/config/configuration.ts` | Host/ports/topic/model path/device defaults. |
| Compose wiring | `docker/compose.summary.yaml` | Connects `pipeline-manager`, `video-ingestion`, `rabbitmq-service`, MinIO, OVMS/audio. |
| Standalone ingestion compose | `video-ingestion/docker/compose.yaml` | Component-level compose for ingestion service. |

## Configured Pipeline Server service

In `docker/compose.summary.yaml`, the `video-ingestion` service is the DL Streamer Pipeline Server integration:

- Image: `${REGISTRY:-}video-ingestion:${TAG:-latest}` built from `video-ingestion/docker/Dockerfile`.
- Port: container `8080`, exposed as `${EVAM_PIPELINE_HOST_PORT}:8080`.
- Healthcheck: `curl -f http://localhost:8080/pipelines -o /dev/null`.
- Runtime mode: `RUN_MODE: EVA`, `REST_SERVER_PORT: 8080`.
- Device: `DETECTION_DEVICE: ${EVAM_DEVICE}`.
- Model mount: `../ov_models:/home/pipeline-server/models`.
- Pipeline cache: `vol_evam_pipeline_root:/var/cache/pipeline_root`.
- Python extension environment:
  - `RABBITMQ_HOST: ${RABBITMQ_HOST}`
  - `RABBITMQ_PORT: 1883`
  - `RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}`
  - `RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}`
  - `MINIO_SERVER: ${MINIO_HOST}:80`
  - `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`

`pipeline-manager` is configured in the same compose file with:

- `EVAM_HOST: ${EVAM_HOST}`
- `EVAM_DEVICE: ${EVAM_DEVICE}`
- `EVAM_PIPELINE_PORT: 8080`
- `EVAM_PUBLISH_PORT: 1883`
- `RABBITMQ_HOST`, `RABBITMQ_AMQP_PORT: 5672`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`

## Pipeline-manager request format

`pipeline-manager/src/evam/services/evam.service.ts` constructs:

```ts
const evamApi = `http://${this.host}:${this.pipelinePort}/pipelines/user_defined_pipelines/${pipeline}`;
```

and sends JSON with `Content-Type: application/json`:

```json
{
  "source": {
    "element": "curlhttpsrc",
    "type": "gst",
    "properties": {
      "location": "http://<minio-host>/<bucket>/<object>"
    }
  },
  "parameters": {
    "detection-properties": {
      "model": "/home/pipeline-server/models/yoloworld/v2/FP32/yolov8l-worldv2.xml",
      "device": "CPU"
    },
    "publish": {
      "minio_bucket": "<datastore.bucketName>",
      "video_identifier": "<stateId>",
      "topic": "topic/video_stream"
    },
    "frame": 5,
    "chunk_duration": 10,
    "frame_width": 480
  }
}
```

Parameter sources:

| Payload field | Source in pipeline-manager |
|---|---|
| `source.properties.location` | `DatastoreService.getObjectURL(state.video.url)` before calling EVAM. |
| `parameters.frame` | `state.userInputs.samplingFrame`. |
| `parameters.chunk_duration` | `state.userInputs.chunkDuration`. |
| `parameters.frame_width` | Hardcoded to `480` in `EvamService.startChunkingStub()`. |
| `parameters.detection-properties.model` | `evam.modelPath` in `pipeline-manager/src/config/configuration.ts`. |
| `parameters.detection-properties.device` | `evam.device`, from `EVAM_DEVICE` or `CPU`. |
| `parameters.publish.minio_bucket` | `datastore.bucketName`, from `MINIO_BUCKET`. |
| `parameters.publish.video_identifier` | The VSS state id passed as `identifier`. |
| `parameters.publish.topic` | `evam.videoTopic`, currently `topic/video_stream`. |

The Pipeline Server returns a pipeline id string. `EvamService.checkChunkingStatus()` polls `GET http://${EVAM_HOST}:${EVAM_PIPELINE_PORT}/pipelines/${pipelineId}` and treats `state === 'COMPLETED'` as done.

## Real pipeline names and templates

`pipeline-manager/src/evam/models/evam.model.ts` defines:

```ts
export enum EVAMPipelines {
  OBJECT_DETECTION = 'object_detection',
  BASIC_INGESTION = 'video_ingestion',
}
```

`EvamService.availablePipelines()` exposes:

- `object_detection` — "Ingestion with Object Detection"
- `video_ingestion` — "Simple ingestion"

`video-ingestion/resources/conf/config.json` defines those same names.

### `object_detection`

Pipeline string:

```text
{auto_source} ! decodebin ! videorate ! videoconvertscale ! video/x-raw,framerate={parameters[frame]}/{parameters[chunk_duration]},format=BGR,width=[1,{parameters[frame_width]}],pixel-aspect-ratio=1/1 ! gvadetect name=detection pre-process-backend=ie ! queue ! gvapython arg=[{parameters[frame]},{parameters[chunk_duration]}] class=Publisher function=process module=/home/pipeline-server/gvapython/publisher/publish.py name=publish ! fakesink
```

The `detection-properties` parameter is mapped as `element-properties` onto the element named `detection`, so the request can set model/device for `gvadetect`.

### `video_ingestion`

Pipeline string:

```text
{auto_source} ! decodebin ! videorate ! videoconvertscale ! video/x-raw,framerate={parameters[frame]}/{parameters[chunk_duration]},format=BGR,width=[1,{parameters[frame_width]}],pixel-aspect-ratio=1/1 ! queue ! gvapython arg=[{parameters[frame]},{parameters[chunk_duration]}] class=Publisher function=process module=/home/pipeline-server/gvapython/publisher/publish.py name=publish ! fakesink
```

This pipeline still declares `detection-properties` in the schema, but the template has no `gvadetect name=detection`; changing those values does not affect the simple ingestion pipeline unless a detection element is added.

## Parameter constraints in `config.json`

Both pipelines define these JSON Schema constraints:

| Parameter | Minimum | Maximum | Default | Effect |
|---|---:|---:|---:|---|
| `frame` | 1 | 64 | 2 | Numerator of output framerate and number of frames per chunk passed to `Publisher`. |
| `chunk_duration` | 2 | 60 | 10 | Denominator of output framerate and chunk duration passed to `Publisher`. |
| `frame_width` | 160 | 800 | 480 | Caps width range `width=[1,{parameters[frame_width]}]`. |

Effective extraction rate is `frame / chunk_duration` frames per second. For example, `frame=2`, `chunk_duration=10` extracts 2 frames per 10-second chunk (0.2 FPS). In `Publisher`, `frames_per_chunk=args[0]`, `chunk_duration=args[1]`, and `frame_timestamp = frame_id * (chunk_duration / frames_per_chunk)`.

## Python publisher behavior

`video-ingestion/src/publish.py` is the sink used by both configured pipelines.

Constructor requirements:

- positional args: `frame`, `chunk_duration` from `gvapython arg=[...]`.
- keyword args through the pipeline parameter named `publish`:
  - `minio_bucket`
  - `video_identifier`
  - `topic`

For each frame, `Publisher.process(frame)`:

1. Reads frame image data and `frame.messages()` metadata from DL Streamer/GVA.
2. Computes `chunk_frame_id = frame_id % frames_per_chunk + 1` and `chunk_id = frame_id // frames_per_chunk + 1`.
3. On chunk change, publishes the previous chunk's message to RabbitMQ MQTT.
4. Saves frame JPEG to MinIO path:
   `video_identifier/frame/chunk_<chunk_id>_frame_<chunk_frame_id>.jpeg`
5. Saves metadata JSON to:
   `video_identifier/metadata/chunk_<chunk_id>_frame_<chunk_frame_id>.json`
6. Adds the frame to a chunk message:

```json
{
  "evamIdentifier": "<video_identifier/stateId>",
  "chunkId": 1,
  "frames": [
    {
      "frameId": 1,
      "chunkFrame": 1,
      "imageUri": "/<bucket>/<video_identifier>/frame/chunk_1_frame_1.jpeg",
      "metadata": { "frame_timestamp": 0.0, "img_format": "BGR" }
    }
  ]
}
```

Object detection metadata appears in `metadata.objects` when the `object_detection` pipeline's `gvadetect` produces GVA messages.

## RabbitMQ path back to pipeline-manager

`Publisher` publishes to MQTT topic `topic/video_stream`. `RabbitmqService` in pipeline-manager connects to RabbitMQ over AMQP using:

- queue: `my_mqtt_queue`
- exchange: `amq.topic`
- routing key: `topic.video_stream` (`/` replaced with `.`)

On receipt, it parses the JSON as `ChunkQueue` and emits `PipelineEvents.CHUNK_RECEIVED`. `PipelineService.triggerChunkCaptioning()` then adds the chunk to state for downstream frame captioning.

## Worked modification: extract 4 frames per 8-second chunk at width 640

If the goal is only to change runtime extraction for one request, do not edit the pipeline template. Change the caller inputs so the request sends:

```json
{
  "parameters": {
    "frame": 4,
    "chunk_duration": 8,
    "frame_width": 640
  }
}
```

In the current code, `frame_width` is hardcoded to `480` in `EvamService.startChunkingStub()`. To expose width as a user setting:

1. Add a user/system config field for frame width in the summary/upload DTO path.
2. Pass it into `startChunkingStub()` or include it in `SummaryPipelineSampling`.
3. Replace the hardcoded `frame_width: 480` with the validated value.
4. Keep the value within `160..800` or update the schema in both pipelines in `video-ingestion/resources/conf/config.json`.
5. Update tests in `pipeline-manager/src/evam/services/evam.service.spec.ts` that currently expect `frame_width: 480`.

Why this works: the pipeline template already uses `framerate={parameters[frame]}/{parameters[chunk_duration]}` and `width=[1,{parameters[frame_width]}]`, and `Publisher` uses the same `frame`/`chunk_duration` values to group frames into chunks.

## Worked modification: add a new detection model for ingestion

The current default model path is hardcoded in `pipeline-manager/src/config/configuration.ts`:

```ts
modelPath: '/home/pipeline-server/models/yoloworld/v2/FP32/yolov8l-worldv2.xml'
```

The container sees models under `/home/pipeline-server/models` because compose mounts `../ov_models` there.

To add or switch a detection model:

1. Put the OpenVINO IR model under `ov_models/...` so it is available inside the container as `/home/pipeline-server/models/...`.
2. If converting a YOLO model, inspect `video-ingestion/resources/scripts/converter.py`; it exports Ultralytics YOLO to OpenVINO and writes FP16/FP32 folders.
3. Update `pipeline-manager/src/config/configuration.ts` to point `evam.modelPath` at the new in-container XML path, or refactor it to read from an environment variable.
4. Ensure the request's `detection-properties.model` and `device` reach the `gvadetect name=detection` element. This only applies to `object_detection` unless a new pipeline includes a detection element named `detection`.
5. Rebuild/restart `pipeline-manager` and `video-ingestion` as needed.
6. Validate with a real POST to `/pipelines/user_defined_pipelines/object_detection` and confirm object metadata under `frames[].metadata.objects`.

## Adding a new pipeline name

To add `my_pipeline`:

1. Add a new entry in `video-ingestion/resources/conf/config.json` under `config.pipelines[]` with `name: "my_pipeline"`, `source: "gstreamer"`, `pipeline`, `parameters`, and `auto_start: false`.
2. Reuse `publish` mapping if the output should continue through VSS:

```json
"publish": {
  "element": { "name": "publish", "property": "kwarg", "format": "json" },
  "type": "object",
  "properties": {
    "minio_bucket": { "type": "string" },
    "video_identifier": { "type": "string" },
    "topic": { "type": "string" }
  }
}
```

3. Keep `gvapython ... name=publish` in the GStreamer string if VSS should receive frames/chunks.
4. Add `MY_PIPELINE = 'my_pipeline'` to `EVAMPipelines`.
5. Add a display entry in `EvamService.availablePipelines()`.
6. Update UI/API tests or config docs that enumerate valid EVAM pipelines.
7. Rebuild `video-ingestion`; its Dockerfile copies the config file into the image.

If a required DL Streamer element, model-proc file, or post-processing setup lives only inside `intel/dlstreamer-pipeline-server:2026.1.0-ubuntu24-rc2`, say so explicitly in docs and use this repo's integration seam (`config.json`, model mount, Python publisher, and request payload) rather than pretending the external image internals are in this repository.

## Validation commands

Use the deployed host/port from your environment. The standalone README shows the same request pattern:

```bash
curl http://${host_ip}:${EVAM_HOST_PORT}/pipelines/user_defined_pipelines/object_detection \
  -H 'Content-Type: application/json' \
  -d '{
    "source": {
      "element": "curlhttpsrc",
      "type": "gst",
      "properties": {
        "location": "http://minio:9000/videosummtest-1/store-aisle-detection.mp4"
      }
    },
    "parameters": {
      "frame": 2,
      "chunk_duration": 10,
      "frame_width": 480,
      "detection-properties": {
        "model": "/home/pipeline-server/models/yoloworld/v2/FP32/yolov8l-worldv2.xml",
        "device": "CPU"
      },
      "publish": {
        "minio_bucket": "videosummtest-1",
        "video_identifier": "video_id_1",
        "topic": "topic/video_stream"
      }
    }
  }'
```

Then poll:

```bash
curl http://${host_ip}:${EVAM_HOST_PORT}/pipelines/<pipeline-id>
```

Expected outcomes:

- POST returns a pipeline UUID/string.
- Status eventually reports `COMPLETED`.
- MinIO contains frame JPEGs and metadata JSON under the requested `video_identifier`.
- RabbitMQ receives one JSON chunk message per chunk on the configured path.
