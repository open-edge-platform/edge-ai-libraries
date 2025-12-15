# Telemetry Metrics

This note explains what the `/telemetry` endpoint returns, how each metric is computed, and how to interpret the numbers when tuning the VDMS DataPrep microservice.

## Endpoint recap

- **Path:** `GET /telemetry`
- **Query parameters:**
  - `limit` (default `10`, max `100`) – number of most recent records to return (capped by the server-side retention window).
  - `source` – optional filter that matches the request path that produced the entry (for example `/videos/upload`).
- **Response shape:**

  ```json
  {
    "count": 1,
    "items": [TelemetryRecord]
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
| `frames_per_second` | Frame extraction throughput. | `frames_extracted / frame_extraction_seconds` (or `/ wall_time_seconds` if extraction time is unknown). |

### Batch breakdown

When SDK mode runs with batching enabled, each batch reports:

- `batch_index` – sequential identifier (starting at `1`).
- `input_frames` and `items_after_detection` – how many frames/crops were submitted for that batch.
- `detection_seconds`, `embedding_seconds`, `storage_seconds`, `total_seconds` – stage timing for the batch, captured before threading overhead is applied.
- `embeddings_stored` – how many embeddings survived all downstream filters.

These entries make it easy to identify skewed batches (for example, ones with large detection times because of busy scenes).
