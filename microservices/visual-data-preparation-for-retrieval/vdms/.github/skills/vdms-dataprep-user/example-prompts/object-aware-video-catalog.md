Build an object-aware video catalog that creates retrieval-ready records for clips containing detected objects, using the VDMS DataPrep stack.

- Bring the stack up if it isn't already; reuse the MinIO credentials and embedding model it was started with.
- Ingest each clip via POST /videos/upload with enable_object_detection=true, a detection_confidence threshold suited to the footage (lower catches more objects, higher favors precision), and content tags for later filtering (e.g. tags=street&tags=vehicles).
- Detected-object crops get their own embeddings in VDMS alongside the frame embeddings, so a separate search layer reading the same VDMS collection can later match queries like "bicycle" against crops and filter by tags — dataprep itself exposes no search endpoint.
- Verify the catalog with GET /videos and GET /telemetry.

Validate the application using:
- Embedding model CLIP/clip-vit-b-32; API base http://localhost:6007/v1/dataprep.
- person-bicycle-car-detection.mp4 from Intel's sample-videos repo (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4) — person, bicycle, and car are all classes the YOLOX detector knows.
- Two ingestions of the clip: detection_confidence=0.85, then 0.5 (renamed copy so the video_id differs), both tagged street.

Expected results:
- Both ingestions return 201 and appear in GET /videos; GET /telemetry records both, with the lower-threshold run generally taking longer since more crops are embedded.
- Detection requires the YOLOX model to have downloaded on first run (network needed); otherwise crops are silently skipped.
