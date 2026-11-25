# Data Intelligence Engine

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/data-intelligence-engine">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/data-intelligence-engine/README.md">
     Readme
  </a>
</div>
hide_directive-->

The Data Intelligence Engine is a FastAPI service that ingests documents, images, videos, audio
and OKF knowledge bundles, embeds them with OpenVINO™ models, and serves retrieval and reranking
over them through one HTTP API. Vectors go to Milvus and concept graphs to NebulaGraph; database
connections are registered at runtime rather than fixed in configuration. The engine listens on
port `16022` by default and ships a web console.

```text
ingest:   files/text -> normalized content blocks -> vector or graph projections
retrieve: query -> document fusion or media search -> optional reranking -> chunks
```

## Features

- **Asset libraries**: a library holds assets, the sources they are materialized into, and the
  pools that bind assets to sources, so one corpus can be indexed by several models side by side.
- **Multimodal ingestion**: PDFs and Office/HTML documents (text chunks plus embedded figures,
  scanned pages through OCR), images, video segments, audio (transcribed, then embedded) and OKF
  concept bundles.
- **Non-blocking ingest**: requests return `202` at once, and each asset reports its progress; a
  digital PDF's text is searchable before its figures are done.
- **Local OpenVINO models** on CPU or Intel GPU: GME for documents, images and transcripts, ViCLIP
  for video, Whisper for speech, PP-DocLayoutV3 for figure detection. A remote OpenAI-compatible
  embedding service also works.
- **Retrieval**: vector, BM25 and concept-graph arms fused with RRF for documents, text-to-media
  search, and optional reranking with bge-reranker or the Qwen3-VL media reranker.
- **Runtime database registry**: Milvus, NebulaGraph and a filesystem content store, registered
  over the API and persisted in the workspace.
- **Web console** at `/console/` for libraries, ingest progress, retrieval and the concept graph.

## Documentation

- [Get Started](./get-start.md)
- [System Requirements](./system-requirements.md)
- [How to Ingest Multimodal Data](./how-to-guides/how-to-ingest-mm-data.md)
- [How to Prepare Models](./how-to-guides/how-to-prepare-models.md)
- [User Guide](./user-guide.md)
- [API Reference](./api.md)
- [Text-to-Media Retrieval](./text-to-media-retrieval.md)
- [Release Notes](./release-notes.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-start.md
./system-requirements.md
./how-to-guides/how-to-ingest-mm-data.md
./how-to-guides/how-to-prepare-models.md
./user-guide.md
./api.md
./text-to-media-retrieval.md
Release Notes <./release-notes.md>

:::
hide_directive-->
