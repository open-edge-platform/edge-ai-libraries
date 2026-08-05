Build an edge preprocessing workflow that turns files from a mounted camera
drop directory into retrieval-ready records.

- Select a supported vector backend (VDMS or Milvus) and media storage backend
  (MinIO or local filesystem).
- Bind the host drop directory to `MM_DATAPREP_INGEST_DATA_ROOT`.
- Submit the relative directory with `POST /media/ingest-dir`; optionally
  recurse and apply camera tags.
- Poll `GET /media/jobs/{job_id}` and report per-item success/error results.
- Inspect `GET /media` and `GET /telemetry` after completion.

Validate with two supported media files tagged for different cameras. Expected
results:

- Submission returns HTTP 202 with a `job_id`.
- Job state reaches `completed` or `completed_with_errors` with a result for
  every accepted item.
- Successful items appear in `GET /media` and have telemetry records.
- A `dir_path` that escapes the configured ingest root is rejected.
