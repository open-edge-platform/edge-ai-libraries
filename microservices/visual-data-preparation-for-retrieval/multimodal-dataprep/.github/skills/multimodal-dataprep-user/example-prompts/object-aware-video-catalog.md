Build an object-aware video catalog for a separate retrieval service.

- Upload clips with `POST /media/upload`, object detection enabled, an
  appropriate confidence threshold, and repeated `tags` query parameters.
- Explain that full frames and detected crops receive embeddings and canonical
  metadata in the selected vector backend.
- Verify ingestion with `GET /media` and `GET /telemetry`.
- Keep query/search behavior in the retriever or application; Multimodal
  DataPrep exposes no semantic-search endpoint.

Compare two renamed copies of one clip at different confidence thresholds.
Expected results:

- Both uploads return HTTP 201 and appear in `GET /media`.
- Telemetry records both pipelines; the number of detected crops may differ.
- The selected VDMS or Milvus collection contains backend-adapted canonical
  metadata suitable for the downstream retriever.
