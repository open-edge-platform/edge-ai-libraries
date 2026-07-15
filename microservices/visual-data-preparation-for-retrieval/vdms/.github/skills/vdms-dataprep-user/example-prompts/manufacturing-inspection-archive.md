Build a manufacturing inspection archive that stores production-line clips with frame and object-crop metadata using the VDMS DataPrep stack.

- Bring the stack up if it isn't already (dataprep + VDMS + MinIO from the prebuilt image); reuse the MinIO credentials and embedding model it was started with.
- Ingest each line clip via POST /videos/upload with a small frame_interval (dense sampling for inspection), enable_object_detection=true, a detection_confidence tuned for the line (default 0.85), and tags identifying line and shift (e.g. tags=line-a&tags=shift-1).
- Each sampled frame gets its own embedding in VDMS; detected-object crops are embedded too; the raw MP4 stays in MinIO.
- Show the archive with GET /videos and per-ingestion timings with GET /telemetry.

Validate the application using:
- Embedding model CLIP/clip-vit-b-32; API base http://localhost:6007/v1/dataprep.
- bottle-detection.mp4 from Intel's sample-videos repo (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4) — bottles on a conveyor, and "bottle" is a class the YOLOX detector knows.
- frame_interval=10, detection enabled, tags line-a.

Expected results:
- The upload returns 201 with status success; GET /videos lists the clip and GET /telemetry shows the ingestion entry.
- The first ingestion downloads the YOLOX model (needs network access — without it, object detection is silently skipped and only frame embeddings are stored).
