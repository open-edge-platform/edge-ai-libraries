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
            "request_id": "a2e00af4-3d62-4d3b-b9e2-5a08743b21b7",
            "source": "/videos/minio",
            "processing_mode": "sdk",
            "timestamps": {
                "requested_at": "2025-12-15T05:18:19.320075Z",
                "completed_at": "2025-12-15T05:18:53.187766Z",
                "wall_time_seconds": 33.42496871948242
            },
            "video": {
                "bucket_name": "video-summary",
                "video_id": "a0ee04eb-5dc2-450b-a4b7-16a230a1c282",
                "filename": "sample.mp4",
                "frame_interval": 20,
                "fps": 30.0,
                "total_frames": 17973,
                "video_duration_seconds": 599.1,
                "tags": [],
                "video_url": "http://vdms-dataprep:8000/v1/dataprep/videos/download?video_id=a0ee04eb-5dc2-450b-a4b7-16a230a1c282&bucket_name=video-summary",
                "video_rel_url": "/v1/dataprep/videos/download?video_id=a0ee04eb-5dc2-450b-a4b7-16a230a1c282&bucket_name=video-summary",
                "processing_mode": "sdk"
            },
            "config": {
                "embedding_mode": "sdk",
                "object_detection_enabled": true,
                "detection_confidence": 0.85,
                "sdk_parallel_workers": 60,
                "sdk_batch_size": 32
            },
            "counts": {
                "frames_extracted": 899,
                "items_after_detection": 2370,
                "embeddings_stored": 2370
            },
            "stages": [
                {
                    "name": "extraction",
                    "seconds": 14.225327968597412,
                    "percent_of_total": 42.55898663057204
                },
                {
                    "name": "detection",
                    "seconds": 388.91471695899963,
                    "percent_of_total": 48.282008923343355
                },
                {
                    "name": "embedding",
                    "seconds": 59.44792938232422,
                    "percent_of_total": 7.380192447729496
                },
                {
                    "name": "storage",
                    "seconds": 14.32844614982605,
                    "percent_of_total": 1.7788119983550996
                }
            ],
            "throughput": {
                "embeddings_per_second": 960.7483555108118,
                "wall_time_embeddings_per_second": 70.9559383300526,
                "embedding_stage_embeddings_per_second": 39.86682168117158,
                "frames_per_second": 63.19713696475425
            },
            "batches": [
               {
                    "batch_index": 29,
                    "input_frames": 3,
                    "items_after_detection": 7,
                    "detection_seconds": 0.8262088298797607,
                    "embedding_seconds": 0.25011181831359863,
                    "storage_seconds": 0.06559395790100098,
                    "total_seconds": 1.1423156261444092,
                    "embeddings_stored": 7
                },
                <other batch details omitted for brevity>
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

Fields such as `embedding_mode`, `object_detection_enabled`, `detection_confidence`, `sdk_parallel_workers`, and `sdk_batch_size` are captured from the resolved runtime configuration. They reflect the **effective** configuration (after environment variables, CLI args, and defaults are merged) so operators can correlate telemetry with tuning changes.

### Aggregate counts

| Field | Description |
| --- | --- |
| `frames_extracted` | Number of keyframes pulled from the source video before detection. |
| `items_after_detection` | Crops + frames that survived object detection filters. |
| `embeddings_stored` | Items that were successfully embedded and written to VDMS. This value should match the `embeddings` counter in the service logs for the same request. |

### Stage timings

Stage timing objects follow the schema `{name, seconds, percent_of_total}` and are produced by `_build_stage_timings`:

1. `seconds` equals the summed time spent in the stage per the pipeline stats.
2. Percentages always add up to `100` even when stages overlap:
   - Extraction runs before anything else, so its percentage is `frame_extraction_seconds / wall_time_seconds`.
   - Detection, embedding, and storage often overlap when the parallel pipeline is enabled. Their raw seconds are normalized against the **parallel budget**, computed as `(wall_time_seconds - extraction_seconds)`. Each stage receives a share of that budget proportional to its measured seconds. This highlights relative pressure inside the concurrently running stages without double-counting wall time.

### Throughput metrics

| Field | Description | Formula |
| --- | --- | --- |
| `embeddings_per_second` | Effective throughput for the entire request. Accounts for overlapping stages. | `embeddings_stored / effective_embedding_seconds`, where `effective_embedding_seconds = wall_time_seconds * (embedding_stage_percent / 100)`. Falls back to `wall_time_seconds` if the embedding stage percent is `0`. |
| `embedding_stage_embeddings_per_second` | Raw throughput during the embedding stage only. Useful for spotting model-level slowdowns. | `embeddings_stored / embedding_seconds_total`. |
| `wall_time_embeddings_per_second` | Wall-clock throughput that ignores stage overlap. | `embeddings_stored / wall_time_seconds`. |
| `frames_per_second` | Frame extraction throughput. | `frames_extracted / frame_extraction_seconds` (or `/ wall_time_seconds` if extraction time is unknown). |

### Batch breakdown

When SDK mode runs with batching enabled, each batch reports:

- `batch_index` – sequential identifier (starting at `1`).
- `input_frames` and `items_after_detection` – how many frames/crops were submitted for that batch.
- `detection_seconds`, `embedding_seconds`, `storage_seconds`, `total_seconds` – stage timing for the batch, captured before threading overhead is applied.
- `embeddings_stored` – how many embeddings survived all downstream filters.

These entries make it easy to identify skewed batches (for example, ones with large detection times because of busy scenes).
