# Data Intelligence Engine

A FastAPI service that ingests documents, images, videos, audio and OKF
knowledge bundles, embeds them with OpenVINO™ models, and serves retrieval and
reranking over them through one HTTP API. Vectors go to Milvus and concept
graphs to NebulaGraph; database connections are registered at runtime rather
than fixed in configuration. The engine listens on port `16022` by default and
ships a web console.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-green)]()

```text
ingest:   files/text -> normalized content blocks -> vector or graph projections
retrieve: query -> document fusion or media search -> optional reranking -> chunks
```

## Features

- Asset libraries: a library holds assets, the sources they are materialized
  into, and the pools that bind assets to sources, so one corpus can be indexed
  by several models side by side.
- Multimodal ingestion: PDFs and Office/HTML documents (text chunks plus
  embedded figures, scanned pages through OCR), images, video segments, audio
  (transcribed, then embedded) and OKF concept bundles.
- Non-blocking ingest: requests return `202` at once, and each asset reports its
  progress; a digital PDF's text is searchable before its figures are done.
- Local OpenVINO models on CPU or Intel GPU: GME for documents, images and
  transcripts, ViCLIP for video, Whisper for speech, PP-DocLayoutV3 for figure
  detection. A remote OpenAI-compatible embedding service also works.
- Retrieval: vector, BM25 and concept-graph arms fused with RRF for documents,
  text-to-media search, and optional reranking with bge-reranker or the
  Qwen3-VL media reranker.
- Runtime database registry: Milvus, NebulaGraph and a filesystem content store,
  registered over the API and persisted in the workspace.
- Web console at `/console/` for libraries, ingest progress, retrieval and the
  concept graph.
- Skills for agent: [`skills/knowledgebase`](skills/README.md) wraps retrieval in a
  `curl` script so an external agent can query the engine and answer from the
  returned chunks.

## Quick Start

This is the minimal path to a running engine and a first retrieval; the
[Get Started guide](docs/user-guide/get-start.md) walks through the same with a sample
file. To ingest more kinds of files, follow
[How to ingest multimodal data](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md).

If you are cloning from the larger monorepo and only need this service, you
can use sparse checkout:

```bash
git clone --filter=blob:none --sparse https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries
git sparse-checkout set microservices/data-intelligence-engine
cd microservices/data-intelligence-engine
```

### Prerequisites

- Docker with Docker Compose v2 ([Installation Guide](https://docs.docker.com/engine/install/ubuntu/)),
  `curl` and `jq`. No Python environment is needed on the host.
- About 50 GB of free disk: the image, the default models and their downloaded
  originals (which can be deleted afterwards).
- Access to Hugging Face for the first run, which downloads the models. Behind a
  proxy, export `http_proxy`/`https_proxy` and configure the Docker daemon's
  proxy for image pulls. If Hugging Face is not reachable, set `HF_ENDPOINT` to a
  mirror.

### Step 1: Deploy

Run the one-click script:

```bash
bash scripts/quickstart.sh
```

The first run builds the image, prepares the default models (GME,
bge-reranker-large, PP-DocLayoutV3, ViCLIP-B, Whisper and the Qwen3-VL INT8
media reranker), starts Milvus and the engine, and registers Milvus as
`local-milvus`. Later runs just start the services. The script also takes
`--models "LIST"` to prepare other models, `--build` to rebuild the image,
`--gpu` to run embedding and reranking on an Intel GPU, and `--down` to stop and
remove the services while keeping the data and models; run it with `--help` for
details. Host-specific settings go in `deployment/docker/.env`, which the script
writes on the first run; a value exported in the shell, such as `ENGINE_PORT`,
overrides it.

### Step 2: Verify

The helper scripts in `scripts/` wrap the HTTP API. Check that the engine is up
and can reach Milvus:

```bash
cd scripts
./status.sh health
./status.sh check local-milvus
```

Then create a library with a text source and a pool, ingest a sentence, and
search it:

```bash
./library.sh create '{"name":"demo"}'
./sources.sh create demo '{"name":"docs","database_id":"local-milvus","collection_name":"demo_docs"}'
./pools.sh create demo '{"id":"docs","name":"Docs","sources":["docs"]}'
./assets.sh create demo '{"asset_pool_ids":["docs"],"text":"Milvus stores the vectors; NebulaGraph stores OKF concept graphs."}' --wait
./retrieve.sh query demo "Where are the vectors stored?" --pool docs --top-k 3
```

The response lists the ingested sentence as a chunk with its score. Open
[http://localhost:16022/console/](http://localhost:16022/console/) to browse the
library and run the same search.

## Optional: Media, PDFs and Concept Graphs

Each content type needs its models prepared and a source configured for it; see
[How to ingest multimodal data](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md):

- [Videos](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md#videos),
  [images](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md#images) and
  [audio](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md#audio) for text-to-media
  search, with [media reranking](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md#7-media-reranking)
  across them.
- [PDFs](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md#pdfs) with figure detection
  (PP-DocLayoutV3) and OCR for scanned pages.
- [OKF knowledge graphs](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md#okf-knowledge-graphs)
  in NebulaGraph, started from `deployment/docker/docker-compose-nebula.yml`.

## Learn More

- [Get Started guide](docs/user-guide/get-start.md) — deploy, ingest a sample file and
  retrieve it.
- [How to ingest multimodal data](docs/user-guide/how-to-guides/how-to-ingest-mm-data.md) —
  PDFs, images, videos, audio, OKF, status checks and media reranking.
- [User guide](docs/user-guide/user-guide.md) — data model, processing pipeline,
  configuration, models, operations and troubleshooting.
- [API reference](docs/user-guide/api.md) — every endpoint.
- [Text-to-media retrieval and media reranking](docs/user-guide/text-to-media-retrieval.md).
- [How to prepare models](docs/user-guide/how-to-guides/how-to-prepare-models.md).
- [Scripts](scripts/README.md) — the deployment scripts and API helpers.
- [Skills for agent](skills/README.md) — the `knowledgebase` skill that lets an
  OpenClaw agent answer from the engine's retrieval results.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## License

Licensed under the [Apache License 2.0](LICENSE).
