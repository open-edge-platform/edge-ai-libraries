# Telemetry Metrics

This note explains what the `/telemetry` endpoint returns, how each metric is computed, and how to interpret the numbers when tuning the VDMS DataPrep microservice.

## Endpoint recap

- **Path:** `GET /telemetry`
- **Query parameters:**
  - `limit` (default `10`, max `100`) – number of most recent records to return (capped by the server-side retention window).
  - `source` – optional filter that matches the request path that produced the entry (for example `/videos/upload`).
- **Response shape:**

Sample response:

```json
{
    "count": 1,
    "items": [
        {
            "request_id": "1dc48f8c-6ee1-4a5c-8d92-032b5bc5591d",
            "source": "/videos/upload",
            "processing_mode": "sdk",
            "timestamps": {
                "requested_at": "2026-04-06T08:05:51.111006Z",
                "completed_at": "2026-04-06T08:08:00.346370Z",
                "wall_time_seconds": 127.636318
            },
            "video": {
                "bucket_name": "vdms-bucket",
                "video_id": "dp_video_1775462750",
                "filename": "input.mp4",
                "frame_interval": 1,
                "fps": 30.0,
                "total_frames": 12552,
                "video_duration_seconds": 418.4,
                "tags": ["intersection", "night"],
                "video_url": "http://:8000/v1/dataprep/videos/download?video_id=dp_video_1775462750&bucket_name=vdms-bucket",
                "video_rel_url": "/v1/dataprep/videos/download?video_id=dp_video_1775462750&bucket_name=vdms-bucket",
                "processing_mode": "sdk"
            },
            "config": {
                "embedding_mode": "sdk",
                "object_detection_enabled": true,
                "detection_confidence": 0.85
            },
            "counts": {
                "stream_id": 0,
                "frames_extracted": 12552,
                "items_after_detection": 8336,
                "embeddings_stored": 20888
            },
            "pipeline_stats": {
                "pipeline_wall_duration": 127.636318,
                "pipeline_throughput_fps": 163.652,
                "pipeline_concurrency_factor": 2.677,
                "pipeline_efficiency_pct": 89.253,
                "parallel_efficiency_pct": 99.34,
                "decode_pipeline_efficiency_pct": 0.8215,
                "detect_pipeline_efficiency_pct": 0.9934,
                "embed_store_pipeline_efficiency_pct": 0.8627
            },
            "stage_duration": {
                "frame_extraction_seconds": 104.857776,
                "detection_seconds": 126.794084,
                "embedding_seconds_total": 80.117875,
                "embed_preprocess_time": 49.012821,
                "embed_inference_time": 30.771018,
                "storage_seconds_total": 29.989046,
                "total_wall_seconds": 127.636318
            },
            "stage_throughput": {
                "decode_throughput": 119.705,
                "detect_throughput": 98.995,
                "embedding_preproc_throughput": 426.174,
                "embedding_infer_throughput": 678.821,
                "embeddings_throughput": 260.716,
                "store_throughput": 696.521,
                "pipeline_throughput": 163.652
            },
            "batches": [
                {
                    "stream_id": 0,
                    "batch_index": 0,
                    "input_frames": 64,
                    "items_after_detection": 18,
                    "detection_seconds": 0.440378,
                    "embedding_seconds": 0.405169,
                    "embedding_preproc_seconds": 0.239543,
                    "embedding_infer_seconds": 0.163761,
                    "storage_seconds": 0.269737,
                    "total_seconds": 1.43656,
                    "embeddings_stored": 82
                },
                "<other batch entries omitted for brevity>"
            ]
        }
    ]
}
```

Each `TelemetryRecord` is stored in JSONL under `data/telemetry/telemetry.jsonl` (or the configured path) and is served verbatim after lightweight normalization so that older float timestamps are converted to UTC ISO-8601 strings.

## Metric derivations

### Timestamps

| Field | Description | Calculation |
| --- | --- | --- |
| `requested_at` | When the pipeline accepted the request. | Captured at the start of processing and emitted as a UTC string (`YYYY-MM-DDTHH:MM:SS.sssZ`). |
| `completed_at` | When the final artifact (embeddings + manifests) was written. | Same formatting as `requested_at`, recorded after storage finishes. |
| `wall_time_seconds` | End-to-end time the request spent in the pipeline. | Difference between the completion and request timestamps (falls back to `0` if either timestamp is missing). |

### Video metadata

This block mirrors the request that was processed:

- `bucket_name`, `video_id`, `filename`, and `frame_interval` are copied from the active job. Numerical fields (`fps`, `total_frames`, `video_duration_seconds`) come straight from the frame extractor.
- `video_url` and `video_rel_url` point to the download endpoint for the processed video or stitched preview.
- `processing_mode` echoes the embedding execution path (`sdk` or `api`).

### Processing config

Fields such as `embedding_mode`, `object_detection_enabled`, and `detection_confidence` are captured from the resolved runtime configuration. When SDK mode is active, `sdk_parallel_workers` and `sdk_batch_size` are also included if configured. All fields reflect the **effective** configuration (after environment variables, CLI args, and defaults are merged) so operators can correlate telemetry with tuning changes.

### Aggregate counts

| Field | Description |
| --- | --- |
| `stream_id` | Identifier of the video stream processed (0-indexed). Useful when multiple streams are processed in a single request. |
| `frames_extracted` | Number of keyframes pulled from the source video before detection. |
| `items_after_detection` | Crops and frames that survived object detection filters. |
| `embeddings_stored` | Items that were successfully embedded and written to VDMS. This value should match the `embeddings` counter in the service logs for the same request. |

### Stage durations

The `stage_duration` block reports the **cumulative** time each stage spent across all processed batches. Because the pipeline is concurrent, individual stage totals can exceed `wall_time_seconds`.

| Field | Description |
| --- | --- |
| `frame_extraction_seconds` | Total time spent decoding frames from the video source. |
| `detection_seconds` | Total time spent running object detection across all batches. |
| `embedding_seconds_total` | Total time for the full embedding stage (preprocessing + inference) across all batches. |
| `embed_preprocess_time` | Time within the embedding stage spent on image preprocessing (resize, normalize). |
| `embed_inference_time` | Time within the embedding stage spent on model inference only. |
| `storage_seconds_total` | Total time spent writing embeddings to VDMS across all batches. |
| `total_wall_seconds` | Same value as `timestamps.wall_time_seconds`; included here for convenience. |

### Pipeline statistics

The `pipeline_stats` block provides concurrency and efficiency metrics computed by `save_batch_results`. All are measured against the true wall-clock interval from the first decode operation to the last store operation.

| Field | Description | Formula |
| --- | --- | --- |
| `pipeline_wall_duration` | True wall-clock duration of the pipeline (seconds). | `(last_store_end_us - first_decode_start_us) / 1_000_000` |
| `pipeline_throughput_fps` | Overall pipeline throughput in frames per second. | `frames_extracted / pipeline_wall_duration` |
| `pipeline_concurrency_factor` | How many seconds of work are completed per wall-clock second. Values greater than 1 indicate effective use of concurrency. | `sum_of_all_stage_totals / pipeline_wall_duration` |
| `pipeline_efficiency_pct` | How efficiently the three concurrent worker threads (decode, detect, embed+store) are utilized. 100 % means all threads are busy the entire time. | `(pipeline_concurrency_factor / 3) × 100` |
| `parallel_efficiency_pct` | How well the slowest (bottleneck) stage fills the pipeline wall time. 100 % means the bottleneck stage ran continuously without idle gaps. | `max(decode, detect, embed, store totals) × 100 / pipeline_wall_duration` |
| `decode_pipeline_efficiency_pct` | Fraction of wall time the decode thread was actively working. | `frame_extraction_seconds / pipeline_wall_duration` |
| `detect_pipeline_efficiency_pct` | Fraction of wall time the detection thread was actively working. | `detection_seconds / pipeline_wall_duration` |
| `embed_store_pipeline_efficiency_pct` | Fraction of wall time the embed+store thread was actively working. | `(embedding_seconds_total + storage_seconds_total) / pipeline_wall_duration` |

### Stage throughput

The `stage_throughput` block reports the per-stage processing rate, making it easy to spot which stage is the bottleneck.

| Field | Description | Formula |
| --- | --- | --- |
| `decode_throughput` | Frame decode rate (frames/s). | `frames_extracted / frame_extraction_seconds` |
| `detect_throughput` | Detection throughput (frames/s). | `frames_extracted / detection_seconds` |
| `embedding_preproc_throughput` | Preprocessing throughput (items/s). | `embeddings_stored / embed_preprocess_time` |
| `embedding_infer_throughput` | Inference throughput (items/s). | `embeddings_stored / embed_inference_time` |
| `embeddings_throughput` | End-to-end embedding stage throughput (items/s). | `embeddings_stored / embedding_seconds_total` |
| `store_throughput` | VDMS write throughput (items/s). | `embeddings_stored / storage_seconds_total` |
| `pipeline_throughput` | Overall pipeline throughput (frames/s). Same value as `pipeline_stats.pipeline_throughput_fps`. | `frames_extracted / pipeline_wall_duration` |

### Batch breakdown

When SDK mode runs with batching enabled, each entry in the `batches` array reports per-batch timing and counts. These entries make it easy to identify skewed batches (for example, ones with large detection times because of busy scenes).

| Field | Description |
| --- | --- |
| `stream_id` | Identifier of the stream this batch belongs to. |
| `batch_index` | Zero-based sequential identifier for the batch within its stream. |
| `input_frames` | Number of raw frames fed into this batch before detection. |
| `items_after_detection` | Frames and crops that passed the detection filter (`total - batch_size`). |
| `detection_seconds` | Time spent running object detection for this batch. |
| `embedding_seconds` | Total embedding time for this batch (preprocessing + inference). |
| `embedding_preproc_seconds` | Time spent on image preprocessing within the embedding step. |
| `embedding_infer_seconds` | Time spent on model inference within the embedding step. |
| `storage_seconds` | Time spent writing this batch's embeddings to VDMS. |
| `total_seconds` | Total end-to-end time for this batch (detect + embed + store). |
| `embeddings_stored` | Number of embeddings successfully stored for this batch. |
