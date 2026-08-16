Onboard a different embedding model into Multimodal DataPrep and verify the
model's supported modalities.

- Pass the model through `EMBEDDING_MODEL_NAME`; Compose maps it to
  `MM_DATAPREP_EMBEDDING_MODEL_NAME`.
- Treat the sibling `multimodal-embedding-serving` model-handler API as the
  contract used by `src/core/embedding/client.py`.
- Use a fresh vector collection when the model's embedding dimension differs.
  For VDMS, override `INDEX_NAME` after sourcing setup. For Milvus, use a valid
  `MILVUS_INDEX_NAME` without hyphens.
- Exercise only modalities reported by the model handler. A text-only model
  should not be expected to ingest images/video successfully.

Validate with:

- `source ./setup.sh --nosetup`, then set the fresh collection variable before
  running Compose.
- `GET /v1/dataprep/health` and verify `embedding_client_status=preloaded`,
  `model_name`, `embedding_device`, and `use_openvino`.
- For a multimodal model, ingest a small MP4 or image with
  `POST /v1/dataprep/media/upload`.
- For a text-capable model, add a summary with `POST /v1/dataprep/summary`.
- Run focused embedding, vector-store, and endpoint tests.

Expected result: supported inputs produce embeddings in the selected backend
without a dimension mismatch; unsupported modalities fail clearly.
