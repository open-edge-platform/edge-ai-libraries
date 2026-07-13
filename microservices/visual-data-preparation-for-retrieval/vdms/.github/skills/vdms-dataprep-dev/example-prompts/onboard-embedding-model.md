Onboard a different multimodal embedding model into the ingestion pipeline and confirm videos embed cleanly with it.

- Wire the new model through EMBEDDING_MODEL_NAME (SDK mode uses the ../../multimodal-embedding-serving path dependency; its EmbeddingModel API is the contract).
- Use a fresh collection to avoid a "Dimensions mismatch" against vectors built with the previous model.
- Verify the health endpoint reports the new model/device in SDK mode. Add the SPDX header to any new file.

Validate the change using:
- After `source setup.sh --nosetup`, set `EMBEDDING_MODEL_NAME=<new-model>` and
  override `INDEX_NAME=<fresh-name>` before invoking Docker Compose.
- Ingest one MP4 via POST /videos/upload on http://localhost:6007/v1/dataprep.
- Check GET /health for the loaded model.

Expected results:
- Health shows the new model; ingestion of the MP4 succeeds with no dimension mismatch (fresh collection).
- Reusing the old collection would surface "Dimensions mismatch"; the fresh-collection fix avoids it.
