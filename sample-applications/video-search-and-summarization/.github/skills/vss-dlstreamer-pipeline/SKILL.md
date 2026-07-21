---
name: vss-dlstreamer-pipeline
description: Helps developers understand and safely modify the DLStreamer/GStreamer Pipeline Server (EVAM) video ingestion pipelines in the video-search-and-summarization sample app. Use when the user wants to change the DLStreamer/GStreamer pipeline, extract frames differently, modify the EVAM pipeline, add a detection model to video ingestion, or tune chunk/frame extraction in the pipeline server.
---

# VSS DLStreamer Pipeline

Use this skill for the Video Search & Summarization sample app when work touches the DL Streamer Pipeline Server-backed video ingestion flow.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It first tries to find an existing VSS checkout -
walking up from the current directory and inspecting the enclosing git repo - and
reuses it **without ever re-cloning**. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/video-search-and-summarization` from `main`. It prints the
resolved app root on stdout:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-dlstreamer-pipeline. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-dlstreamer-pipeline"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it.

## Ground truth first

Before editing, read these repo paths; do not infer pipeline names or payloads from generic DL Streamer examples:

- `video-ingestion/resources/conf/config.json` - the actual pipeline definitions loaded into the DL Streamer Pipeline Server image.
- `video-ingestion/src/publish.py` - `gvapython` sink that writes frames/metadata to MinIO and publishes chunk messages.
- `pipeline-manager/src/evam/models/evam.model.ts` - request DTO and `EVAMPipelines` enum.
- `pipeline-manager/src/evam/services/evam.service.ts` - endpoint and request body sent to EVAM.
- `pipeline-manager/src/config/configuration.ts` and `docker/compose.summary.yaml` - host, ports, model path, device, RabbitMQ, MinIO wiring.
- For architecture language, see `docs/user-guide/how-it-works/*.md`; `docs/user-guide/how-it-works.md` references `_assets/TEAI_VideoPipelines.png`.

## Actual flow in this repo

1. The summary pipeline stores the input video in MinIO and obtains an HTTP object URL.
2. `pipeline-manager/src/state-manager/services/pipeline.service.ts` calls `EvamService.startChunkingStub(stateId, videoUrl, state.userInputs, state.systemConfig.evamPipeline)`.
3. `EvamService` POSTs to:

   ```text
   http://${EVAM_HOST}:${EVAM_PIPELINE_PORT}/pipelines/user_defined_pipelines/${pipeline}
   ```

   where `${pipeline}` is one of the real configured names:
   - `object_detection`
   - `video_ingestion`

4. DL Streamer Pipeline Server executes the matching GStreamer template from `video-ingestion/resources/conf/config.json`.
5. Frames pass through `gvapython ... class=Publisher function=process module=/home/pipeline-server/gvapython/publisher/publish.py`.
6. `Publisher` writes frame JPEGs and metadata JSON to MinIO and publishes a chunk message to RabbitMQ MQTT topic `topic/video_stream`.
7. `pipeline-manager/src/evam/services/rabbitmq.service.ts` consumes AMQP queue `my_mqtt_queue` bound to exchange `amq.topic` with routing key `topic.video_stream`, then emits `CHUNK_RECEIVED`.
8. Captioning, summarization, and search embedding generation happen downstream from the extracted frames/metadata; EVAM itself only chunks/extracts/detects/publishes in this repo.

## Request payload shape

`EvamService.startChunkingStub()` sends this shape:

```json
{
  "source": {
    "element": "curlhttpsrc",
    "type": "gst",
    "properties": { "location": "<MinIO object URL>" }
  },
  "parameters": {
    "detection-properties": {
      "model": "/home/pipeline-server/models/yoloworld/v2/FP32/yolov8l-worldv2.xml",
      "device": "CPU"
    },
    "publish": {
      "minio_bucket": "<pipeline-manager MINIO_BUCKET>",
      "video_identifier": "<stateId>",
      "topic": "topic/video_stream"
    },
    "frame": 5,
    "chunk_duration": 10,
    "frame_width": 480
  }
}
```

`frame`, `chunk_duration`, and `frame_width` are validated by JSON Schema in `video-ingestion/resources/conf/config.json`.

## Pipelines as defined in `video-ingestion/resources/conf/config.json`

- `object_detection`:
  `... videorate ! videoconvertscale ! video/x-raw,framerate={parameters[frame]}/{parameters[chunk_duration]},format=BGR,width=[1,{parameters[frame_width]}],pixel-aspect-ratio=1/1 ! gvadetect name=detection pre-process-backend=ie ! queue ! gvapython ... ! fakesink`
- `video_ingestion`:
  same decode/rate/scale/publish chain, but without `gvadetect`.

The `detection-properties` request parameter maps to the element named `detection`, so it only has an effect when the selected pipeline contains `gvadetect name=detection`.

## Safe modification workflow

GStreamer pipeline strings are fragile: a missing `!`, caps typo, bad element name, or parameter mismatch can make the pipeline fail at runtime even if TypeScript compiles.

When changing extraction behavior:

1. Edit `video-ingestion/resources/conf/config.json` first.
2. Keep parameter placeholders aligned with the request DTO and schema: `{parameters[frame]}`, `{parameters[chunk_duration]}`, `{parameters[frame_width]}`, `publish`, and any element-property mappings.
3. If adding a new selectable pipeline, also update:
   - `pipeline-manager/src/evam/models/evam.model.ts` (`EVAMPipelines`)
   - `pipeline-manager/src/evam/services/evam.service.ts` (`availablePipelines()`)
   - UI/API config paths that expose `evamPipeline` if needed.
4. If adding/changing a detection model, ensure the model is available under the container mount `/home/pipeline-server/models` (`../ov_models` in `docker/compose.summary.yaml`) and update `pipeline-manager/src/config/configuration.ts` model path or make it configurable.
5. Rebuild/restart `video-ingestion`; `video-ingestion/docker/Dockerfile` copies `resources/conf/config.json` into `/home/pipeline-server/config.json` and copies `src/` into `/home/pipeline-server/gvapython/publisher/`.
6. Validate with `GET /pipelines`, then POST a real `object_detection` or `video_ingestion` request and confirm:
   - the POST returns a pipeline UUID,
   - `GET /pipelines/{id}` reaches `COMPLETED`,
   - MinIO contains `video_id/frame/chunk_N_frame_M.jpeg` and metadata JSON,
   - RabbitMQ delivers chunk messages.

See `references/evam-pipelines.md` for the detailed request/config reference and a worked modification example.
