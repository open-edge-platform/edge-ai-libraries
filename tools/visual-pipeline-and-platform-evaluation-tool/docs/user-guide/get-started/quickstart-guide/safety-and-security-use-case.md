# Safety and Security Use Case

The **Safety and Security** use case focuses on person-centric video analytics for environments such
as entrances, corridors, store aisles, and other monitored public areas where visibility into movement
and activity is important.

This guide walks you through the **People Detection and Tracking** predefined pipeline, which is one
of the pipelines used to benchmark this use case in ViPPET.

The predefined variant runs on **GPU** and chains person detection, person re-identification,
Deep SORT tracking, FPS reporting, and optional output/metadata publishing.

## Target use case

Use this pipeline when you need to:

- keep persistent track IDs across short occlusions,
- benchmark person-tracking throughput on Intel GPU with DL Streamer.

It is best suited to fixed-camera or low-motion camera scenes such as entrances,
store aisles, corridors, and public-area monitoring.

## Pipeline workflow and supported models

The predefined variant contains this runtime sequence:

1. `gvadetect` with `yolo11s` (`INT8`) on GPU (`threshold=0.5`) finds person ROIs.
2. `gvainference` with `mars-small128` (`FP32`) on GPU computes person embeddings for Re-ID.
3. `gvatrack` with `tracking-type=deep-sort` links detections across frames into stable tracks.
4. `gvafpscounter` measures throughput after warm-up (`starting-frame=100`).
5. `gvawatermark` draws boxes/labels when rendered output is enabled.
6. `gvametaconvert` + `gvametapublish` can emit JSON-lines metadata.

Deep SORT parameters used in the predefined variant:

- `max_age=60`
- `max_cosine_distance=0.3`
- `object_class=person`
- `reid_max_age=30`

## Role of tracking and optional classification

- **Tracking (default):** Deep SORT is responsible for temporal continuity and stable IDs.
  The Re-ID stage (`mars-small128`) helps preserve identities through short partial occlusions
  and re-entries.
- **Optional classification (user extension):** If your use case needs per-person attributes
  (for example PPE or role labels), add a classification stage after detection/tracking and
  keep `inference-region=roi-list` plus `object-class=person` so only person ROIs are classified.

## Expected input video characteristics

The predefined benchmark clip is `people-detection-and-tracking.mp4` with:

- resolution: `2560x1440`
- frame rate: `~29.97 FPS`
- codec: `H.264`
- duration: `~23.79 s`

For consistent behavior on your own content, prefer:

- mostly static or smoothly moving camera,
- visible full/upper body people at moderate scale,
- limited motion blur and no extreme strobing,
- crowd density similar to the baseline if you compare FPS directly.

## Prerequisites for reproducible benchmarking

Before benchmarking, confirm:

1. The GPU profile is enabled when starting ViPPET (`COMPOSE_PROFILES` includes `gpu`).
2. Both models are installed:
   - `ultralytics/public/yolo11s/INT8/yolo11s.xml`
   - `ultralytics/public/mars-small128/mars_small128_fp32.xml`
3. Input video source is fixed for all compared runs (same file, same resolution/FPS).
4. Benchmark mode is fixed across runs (same stream count, runtime, output mode, metadata mode).
5. No additional heavy workloads are running on the same host during measurements.

## Step 1. Open the predefined pipeline

1. Open the ViPPET UI and navigate to **Pipelines**.
2. Select **People Detection and Tracking**.
3. Open the **GPU** variant in Pipeline Builder.

## Step 2. Verify key configuration

In Pipeline Builder, verify the following defaults for the predefined pipeline:

| Node | Default | Description |
|------|---------|-------------|
| **Object Detection** (`gvadetect`) | `yolo11s INT8`, `device=GPU`, `threshold=0.5` | Detects person ROIs on the GPU and establishes the baseline detection sensitivity used by the pipeline. |
| **Re-ID Inference** (`gvainference`) | `mars-small128 FP32`, `device=GPU`, `inference-region=roi-list`, `object-class=person` | Computes person embeddings for re-identification on detected ROIs only, which helps preserve track identity across brief occlusions and re-entries. |
| **Tracker** (`gvatrack`) | `tracking-type=deep-sort` | Links detections over time into stable person tracks using Deep SORT. |

For benchmark parity, keep these defaults unchanged and only vary one factor at a time
(for example stream count or output mode).

## Step 3. Run in ViPPET

For benchmark runs, use **Performance Testing**:

1. Go to **Performance**.
2. Choose the **People Detection and Tracking (GPU)** variant.
3. Set stream count and runtime.
4. Select output and metadata modes (see next section).
5. Start the run and monitor FPS plus hardware metrics.

## Live output vs non-live output behavior

Output mode changes the measured workload:

- `disabled`: no rendered output is persisted. This is the preferred mode for raw inference/tracking throughput.
- `file`: encoded output video is written to disk. Includes encoding and I/O overhead.
- `live_stream`: output is encoded and sent to RTSP (`mediamtx`). Includes encoding and streaming overhead.

In most environments, expected throughput ordering is:

`disabled >= file >= live_stream`

Use the same output mode across runs you compare.

## Metadata handling

`gvametapublish` records are JSON-lines. In ViPPET:

- `metadata_mode=disabled`: metadata files are not produced by execution config injection.
- `metadata_mode=file`: per-stream metadata files are produced and can be read from job endpoints.

For real-time consumers during performance tests, use SSE metadata stream endpoints from the job status
(`metadata_stream_urls`) when available.

## Known limitations

- The predefined pipeline currently ships as **GPU-only** variant.
- It is tuned for **person** tracking; non-person tracking is out of scope for the predefined setup.
- Strong camera shake, heavy occlusion, severe blur, or abrupt lighting shifts can degrade ID stability.
- FPS from this pipeline should not be compared directly with detection-only pipelines without accounting
  for added Re-ID and tracking stages.

## Benchmarking expectations

When analyzing results, interpret metrics in this order:

1. **Per Stream FPS** for the primary throughput comparison.
2. **Total FPS** for host-level capacity checks.
3. **Latency metrics** (if enabled) for responsiveness and jitter.
4. **Metadata quality checks** (track continuity, ID switches) on representative clips.

For stable conclusions, run at least 3 repetitions per configuration and compare median values.
