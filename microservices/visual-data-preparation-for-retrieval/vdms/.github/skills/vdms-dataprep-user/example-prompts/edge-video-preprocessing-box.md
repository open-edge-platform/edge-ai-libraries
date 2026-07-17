Build an edge video preprocessing box: a small watcher that runs near the cameras and turns each new MP4 into retrieval-ready data locally, before any central sync.

- Bring the full stack up on the edge host (dataprep + VDMS + MinIO, all local); export strong MinIO credentials in-shell and reuse the same pair across restarts.
- Watch a drop folder; on each new MP4, POST /videos/upload with a moderate frame_interval and a per-camera tag (e.g. tags=camera-1).
- Raw MP4s land in MinIO (console on :6011), embeddings and metadata in the local VDMS collection — everything stays on the box; a later sync job can read MinIO and VDMS directly.
- Report per-file ingestion status and rolling GET /telemetry timings.

Validate the application using:
- Embedding model CLIP/clip-vit-b-32; API base http://localhost:6007/v1/dataprep.
- Two clips from Intel's sample-videos repo (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4) dropped one after another: car-detection.mp4 (tag camera-1) and people-detection.mp4 (tag camera-2).

Expected results:
- Each drop returns 201 and the clip appears in GET /videos; the MinIO console shows the raw files; GET /telemetry shows two ingestion entries.
- Stopping and restarting the stack with the same credentials keeps the library intact (the MinIO volume and VDMS collection persist).
