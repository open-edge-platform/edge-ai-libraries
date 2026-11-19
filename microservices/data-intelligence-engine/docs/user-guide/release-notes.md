# Release Notes: Data Intelligence Engine

## Version 2026.3.0

**Release Date**: November 30, 2026

This development version provides a multimodal ingestion and retrieval
service for local enterprise knowledge, with OpenVINO inference and a unified HTTP API.

**New**:

- **Asset library management**: organizes assets, sources and pools so the same
  corpus can be indexed with multiple models and database backends.
- **Multimodal ingestion**: processes PDF, Office and HTML documents, images,
  videos, audio and OKF knowledge bundles, including embedded figures and OCR
  for scanned pages.
- **OpenVINO model inference**: runs GME, ViCLIP, Whisper and PP-DocLayoutV3 on
  CPU or Intel GPU, with an alternative OpenAI-compatible remote embedding backend.
- **Hybrid document retrieval**: combines vector, BM25 and concept-graph results
  with reciprocal rank fusion, with optional document reranking.
- **Text-to-media retrieval and reranking**: searches images, video segments and
  audio transcripts, with optional Qwen3-VL media reranking.
- **Web console and agent integration**: provides a browser console for libraries,
  ingestion, retrieval and concept graphs, plus a reusable `knowledgebase` skill
  for external agents.
- **Containerized deployment**: includes a one-click Docker Compose workflow to
  build the service, prepare models, start Milvus and register the database.