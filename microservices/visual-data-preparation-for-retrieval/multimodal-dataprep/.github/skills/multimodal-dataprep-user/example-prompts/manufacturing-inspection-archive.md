Build a manufacturing inspection archive containing both production-line video
and still images.

- Start a supported DataPrep stack and retain its backend credentials and
  collection configuration.
- Upload clips and inspection images with `POST /media/upload`.
- Use a small video `frame_interval`, enable object detection, tune
  `detection_confidence`, and add line/shift tags as query parameters.
- Verify the stored assets through `GET /media` and ingestion timings through
  `GET /telemetry`.

Expected results:

- Each upload returns HTTP 201 with success status.
- Videos produce sampled-frame embeddings and optional detected-crop
  embeddings; images produce whole-image and optional crop embeddings.
- Records are written through the selected VDMS or Milvus backend, while raw
  assets use the selected MinIO or local storage backend.
- If YOLOX cannot initialize, the logs explain why crop embeddings are absent.
