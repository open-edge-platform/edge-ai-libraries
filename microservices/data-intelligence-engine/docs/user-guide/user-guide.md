# Data Intelligence Engine User Guide

This guide explains the engine's data model, processing pipeline, runtime state,
configuration, and console. [Get started](get-start.md) takes a clean machine
from building the image to a first retrieval. For routes and payload
examples, see the [API reference](api.md).

## Contents

- [Core Concepts](#core-concepts)
  - [Asset libraries](#asset-libraries)
  - [Adding and indexing assets](#adding-and-indexing-assets)
  - [Databases and sources](#databases-and-sources)
- [Asset Content](#asset-content)
- [Processing Pipeline](#processing-pipeline)
  - [Blocks to vector nodes](#blocks-to-vector-nodes)
  - [Blocks to knowledge](#blocks-to-knowledge)
  - [Source filtering](#source-filtering)
  - [Vector data path](#vector-data-path)
  - [Retrieval default and RRF fallback](#retrieval-default-and-rrf-fallback)
  - [Multiple vector sources and score scales](#multiple-vector-sources-and-score-scales)
  - [Multimodal retrieval and reranking](#multimodal-retrieval-and-reranking)
- [Workspace](#workspace)
- [Console](#console)
  - [Graph view and retrieval traces](#graph-view-and-retrieval-traces)
- [Configuration](#configuration)
  - [Compose deployment](#compose-deployment)
  - [Remote document embedding](#remote-document-embedding)
- [Models](#models)
- [Operations](#operations)
  - [When attaching a source fails](#when-attaching-a-source-fails)
- [Source Map](#source-map)

## Core Concepts

### Asset libraries

An `AssetLibrary` is one set of assets plus the machinery that keeps them
materialized. It owns three registries:

- **Assets** are recognizable input objects, such as files or inline text. Each
  asset carries the origin from which it was read.
- **Sources** identify external storage locations. Each source names a registered
  database and collection.
- **Asset pools** group asset IDs and attach sources. A pool owns one internal
  projection per source and tracks how far each source has synchronized.

`FileAssetLibrary` is the RAG specialization. It defines file identity, content
storage, projection selection, file listing/removal, and API chunk conversion.
Every operation names an asset library by name or ID; the engine has no active
or implicit current library.

### Adding and indexing assets

Adding content and indexing it are related but distinct operations:

1. Uploading stages bytes in the shared upload directory; it does not change a
  library. A browser can stage a file with
  `PUT /v1/libraries/{library}/uploads/{path}`, sending the raw bytes as the
  body. `{path}` may contain folders, and the response's `name` is what
  `file_paths` takes in the next step.
2. `POST /v1/libraries/{library}/assets` returns stable asset IDs with `202`
  and `status: "materializing"` before extraction. A background task extracts,
  stores and registers the content.
3. Supplying `asset_pool_ids` in that request assigns the assets to those pools
  and starts background indexing. An empty list stores without indexing.
4. `POST /v1/libraries/{library}/asset_pools/{pool}/assets` assigns already
  registered asset IDs without uploading or extracting content again.

`DELETE /v1/libraries/{library}/assets` (body `{"asset_ids": [...]}`) removes
assets and everything derived from them: the stored content, their chunks in
every vector source, and, for an OKF bundle, its concepts in every graph source
and their vectors in the `{collection}_concept` collection, except concepts
another remaining bundle in the same source also defines. Documents write
nothing to graph sources, but concepts that stay and cite a deleted document's
chunks are rewritten to cite only what is left, so graph retrieval stays valid.
Everything is planned before anything is changed: if a source is unavailable,
or a deleted OKF bundle's files can no longer be read, the request fails and
nothing is removed.

The immediate response has no `warnings`: it has not inspected the content yet.
Poll the asset listing until every returned ID is present and its
`materialization` reaches `ready` (`text_ready` means only the document's first
text phase is searchable). Per-source pool status separately reports whether
indexing is pending, ready, or failed. Re-adding the same file updates its
existing asset and refreshes every pool that already contains it.

After extraction, `GET /v1/libraries/{library}/assets/{asset_id}/enrichment`
reports media embedding coverage, including `embedding_status: "no_source"`
and `embedding_reason` when no serving source handles the media. Caption and
transcript jobs are registered in the background after extraction and run
after initial sync, in that order. Materialization `ready` does not wait for
these jobs; for audio wait for both `transcript_status: "completed"` and
`embedding_status: "ready"`. Without a video-summary URL captions are
`skipped`. Pool readiness alone is insufficient, particularly for an initially
empty pool that may already be ready before extraction starts.

A projection holds the machinery it uses rather than inheriting from it. A
vector projection owns its index and retrievers; a graph projection owns its
graph adapter. Projections are internal to pools and are not API resources.

### Databases and sources

Database registrations are runtime state, not environment configuration. A
source references a database registration by ID and supplies a collection name.
The database manager creates adapters lazily on first use.

Supported backends are:

| Type | Backend | Status |
|---|---|---|
| `vector` | Milvus | Vector indexing and retrieval are implemented. |
| `object` | Filesystem | Asset content storage is implemented. |
| `graph` | NebulaGraph | OKF concept-graph ingest and graph/RRF retrieval are implemented; general property-graph write-back is limited. |

Use `GET /v1/databases/backends` to inspect the registrations accepted by
the running version. See the [database API](api.md#databases) for lifecycle and
failure behavior.

## Asset Content

One file is one asset, regardless of file type or how many pieces extraction
produces. Re-ingesting the same origin updates the same stable asset ID instead
of creating a duplicate.

An asset's bytes and normalized content live in an object source. A library uses
one content container, created on first ingest. The persisted library stores
references rather than embedding the corpus in its configuration.

The filesystem layout within a content container is:

```text
blobs/<sha256>              immutable binary data shared by identical content
assets/<asset-id>.json      one asset's normalized content stream
```

A content stream is an ordered sequence of typed blocks: text, table, image,
audio, or video. Blocks carry layout metadata such as page, bounding box, and
reading order. Extracted document images are stored as blobs. Standalone media
instead keeps a `file://` reference to the uploaded or external original, with
no second blob copy; that file must remain available while the asset exists.
Deleting assets removes engine-owned media inside the upload directory and
reports it in `files_removed`; files outside it are retained in `files_kept`.

`core/extractor.py` selects an extractor from the MIME type:

- Text uses the llama-index reader.
- PDF uses pdfplumber for its text layer and pypdfium2 for rendered pages.
- Standalone media becomes one binary block.

A new file format can be added as another extractor that produces the same
content-stream contract.

## Processing Pipeline

### Blocks to vector nodes

`VectorIndexer._block_nodes`, shared by batch and streaming paths, parses each
accepted block independently and skips multimodal-derived roles. Every resulting
chunk therefore keeps the page and bounding box of its source block. Layout
coordinates remain as record metadata but are excluded from embeddings.

A document figure (`role: "doc_image"`) becomes one image node. A document
source using the `local_openvino` GME document package has a `text` profile and uses
`VectorIndexer`; GME embeds the image jointly with its reference text (fused),
or surrounding prose when no caption is available. It can retain a figure with
pixels alone. A text-only embedding model falls back to the caption/prose and
skips a figure with neither. Digital PDFs and illustrated structured documents
are materialized in two phases: prose first, figures second.

Standalone media sources use `MultimodalIndexer` and their own model's vectors
(ViCLIP-B by default for short video, GME for images and derived text). User-selected pools
choose the path: a standalone image sent to a document pool still follows its
document source's fused path. A GME media source also supports `doc_image`;
duplicate indexing occurs only if the user explicitly co-locates it with a
document source and permits those image blocks. Keep document and media pools
separate, or narrow `asset_types`, `block_kinds` and `block_roles` when sharing.

A GME media source embeds image pixels only; captions remain display text.
`target_media` selects sources and blocks, not how their vectors are indexed.

A chunk never spans blocks. A block shorter than the chunk size (`512`, or the
source's `operator_options.chunk_size`) remains a short chunk rather than
merging with the next block.

### Blocks to knowledge

A graph source holds OKF concepts, not document blocks. Its knowledge
(`core/knowledge/`) has two steps:

- `extract` turns documents into OKF bundles through an external extractor
  service. All documents form one task: first review the full corpus and generate
  task-specific instructions, then extract/merge the OKF bundle using those
  instructions. Inputs and OKF bundles are exchanged through the shared upload
  directory; HTTP returns JSON naming the completed bundle, never a ZIP.
- `build` turns OKF bundles into a graph: each concept a vertex keyed by its
  concept id and labelled by its type, each link an edge, and the concept's
  provenance (`source_chunk_ids`, the document chunks it was drawn from) kept in
  the vertex so graph retrieval can walk from concepts back to text.

Each graph source's `GraphIndexer` holds one `Knowledge` and materializes what
`build` returns into its graph database (vertices, then edges). Different kinds
of knowledge belong in separate graph sources, each with its own space.

Which formats a graph source builds from is its `operator_options.asset_types`:

| `asset_types` | Accepts | Notes |
|---|---|---|
| unset or `["okf"]` | OKF bundles | The default. |
| `["okf", "document"]` | OKF bundles and documents | Needs `external_extractor` and a vector source for chunk provenance. |

```json
{
  "operator_options": {
    "asset_types": ["okf", "document"],
    "external_extractor": {
      "url": "http://okf-extractor:8080",
      "api_key": "...",
      "timeout": 1800,
      "trigger": "auto",
      "options": {}
    }
  }
}
```

`url` is required (http or https); `api_key` is optional and reported as `***`;
`timeout` is seconds to wait for the extractor (default 3600); `trigger` decides when
extraction runs (below); `options` is passed to the service. Creating a graph source with any other format, with `document` but not
`okf`, or with a missing or invalid extractor fails with 400. Document chunks
always live in vector sources, where concepts cite them.

The extractor settings must be nested under `operator_options.external_extractor`,
not pasted directly into `operator_options`. The latter is rejected with a
configuration error rather than silently creating an OKF-bundle-only source.
Use [the complete source example](../../scripts/example/graph-source-with-extractor.json)
when creating a document-extracting graph source.

The engine stages persisted content blocks/captions in `ENGINE_UPLOAD_DIR` and
sends only relative file references to the extractor. Both services must mount
the same writable upload folder (by default the workspace's uploads directory).
The optional Compose stacks use the same `ENGINE_UPLOAD_PATH` host directory,
defaulting to the uploads subdirectory of `ENGINE_WORKSPACE_PATH`. Relative
paths let each process use its own absolute mount location.

Extraction runs as a background **job**, not as part of syncing. A pool sync
indexes documents into the vector sources and only records that the graph
source's extraction is out of date; the graph source stays `ready` and keeps
serving (and building uploaded bundles) while an extraction runs. When a job
runs depends on `trigger`:

| `trigger` | When extraction runs |
|---|---|
| `"auto"` or `{"mode": "auto", "debounce_seconds": 15}` | After document materialization/sync, a job waits for `debounce_seconds` without another document change (default 15, `0` to start at once), so a bulk upload is one extraction. Unchanged pool syncs do not restart the timer. |
| `{"mode": "schedule", "cron": "0 2 * * *", "timezone": "Asia/Shanghai"}` | At each matching minute of the 5-field cron expression (`timezone` defaults to UTC), only if documents changed since the last extraction. Minutes missed while the engine is down are not caught up. |
| `"manual"` | Only when requested with `POST .../asset_pools/{pool}/extractions`. |

A request through the API always works, whatever the trigger, and starts a
debounced job at once.

A job extracts the pool's whole current document corpus, so task instructions
and entity identities do not depend on which documents changed. One job per
pool and source is active at a time: a request while one is queued returns it;
a request while one is running returns it and runs once more afterwards, so
documents added meanwhile are covered. A job finding nothing changed since the
last extraction ends `up_to_date` (use `force` to extract anyway). The source's
status reports it as `extraction`: `trigger`, `state` (`idle`, `queued`,
`running`), `outdated`, `bundle_asset_id`, and the `active` and `last` job.
A `schedule` trigger also reports `next_run`. `outdated` is persisted; job
history is kept in memory for the engine's run. The trigger is fixed when the
source is created.

The delay is a quiet period after document indexing, not a promise that the
extractor receives a request that many seconds after the upload's `202` response.
Initial content extraction/vector indexing may take longer, and an existing
extraction for the same source must finish before its follow-up can run. That
follow-up waits only for quiet time not already spent waiting for the running job.

Inspect the pool's `extraction.trigger_options.debounce_seconds` for the effective
delay and `extraction.active.not_before` for the queued deadline (also returned by
the extraction-job API). A queued job without `not_before` is eligible and waiting
for a worker; a running job has started. Changing a code default requires rebuilding
and recreating the engine container, and does not override a source's explicit
`debounce_seconds`. `timeout` controls the extractor HTTP request, not this delay.

In the console, a pool's graph source shows its extraction state (hover for
the trigger, next run and last result) with an **Extract now** button, in the
pool table and on the canvas.

`status` continues to mean projection-sync state internally. The API also returns
`display_status` on each source status and on the pool, combining that sync state
with OKF extraction readiness. The console uses this combined status everywhere:
**Extraction waiting**, **Extraction queued**, **Extracting…**, **Extraction
needed** (including manual/scheduled work), or **Extraction failed** instead of
showing a graph as ready while its generated knowledge is behind. It becomes
ready only after extraction and graph materialization finish. A vector source
can independently be ready while the graph keeps working.

A finished job publishes the bundle as an ordinary `okf` asset of the pool:
`uploads/<library-id>/okf-extracted/<pool>-<source>-<id>/`, registered in the
library and the pool, so it appears in the asset list, the console and the API
like an uploaded bundle. The job then syncs the pool, which builds it into the
graph and the concept index. Its `task.json` manifest maps logical source paths
to document asset IDs, so provenance resolves by asset ID (inline content and
duplicate filenames work). Re-extraction updates the same asset in place;
concepts the new bundle no longer has are retired from the graph and the
concept index. Deleting documents marks the extraction outdated and rebuilds
the generated bundle without them; deleting a pool's last document removes it.
A failed job (its `error` says why) leaves the previous bundle in place and the
graph source `ready`.

**Uploaded and generated bundles.** You can always upload OKF bundles, whatever
the trigger and whether or not an extraction is running; they are built right
away and never touched by extraction. Where an uploaded bundle and the
generated one define the same concept (same type and title), the uploaded
version wins -- its type, title, summaries and body -- and keeps the relations
and chunk citations only the generated one has. The result does not depend on
which was built first. Deleting the uploaded bundle restores the generated
version. The pool graph (`GET .../graph`, and the console's concept graph,
which rings overrides) reports each concept's `origin`: `uploaded`,
`generated` or `both`. To correct an extracted concept, upload a bundle defining it; to stop
extraction for a pool, use a `manual` source and delete the generated bundle.

The standalone service exposes `POST /v1/tasks` for JSON task metadata and shared
`file_path` references (or inline text blobs), and `GET /health`. A successful
response contains `task_id`, `bundle_path` relative to the shared upload folder,
and `concept_count`. The engine validates the completed shared folder and
publishes it as the pool's extracted bundle asset (above). There are no archive or multipart file transfers. Non-empty task
instruction overrides, a `goal`, and a summary `language` can be supplied in
`external_extractor.options`. Model access and execution limits remain server
configuration. See the [OKF service guide](../../tools/okf_extractor/README.md) for
schemas, the two-stage pipeline, and the optional Compose deployment. Synchronous
tasks may need a timeout longer than the default 3600 seconds.

### Source filtering

A pool may hold more assets than one source accepts. Configure a source with an
asset filter such as:

```json
{
  "operator_options": {
    "asset_types": ["pdf", "image/*"]
  }
}
```

Values may be extensions, MIME types, or MIME families. For a graph source
`asset_types` means knowledge formats instead (see above). Synchronization computes
indexed assets, missing assets, and revision progress against each source's own
accepted subset. This prevents a filtered source from remaining permanently
behind the pool revision.

### Vector data path

```text
create asset library
  -> register a source backed by a database collection
  -> create a pool and attach source IDs
  -> ingest files into content streams and register assets
  -> add assets to a pool
  -> synchronize each source's accepted assets
  -> parse blocks into nodes and materialize them through the adapter
  -> retrieve with vector search and optional BM25/RRF
  -> optionally rerank the merged chunks
```

A pool never assumes an attached collection is empty. It asks each projection
which requested asset IDs are already present and indexes only the difference.
This also repairs progress after restart and reindexes records deleted out of
band.

Milvus I/O stays behind `VectorAdapter`; `VectorStoreIndex` owns embedding and
search. Record hydration and metadata deletion use the adapter directly because
the index does not expose those operations.

### Retrieval default and RRF fallback

`POST /v1/retrieve` defaults `retriever_type` to `rrf`. RRF fuses a pool's
vector, BM25, and graph arms, but a pool with no graph source has nothing a
fusion adds over its vector arm, so such a pool falls back to plain vector
similarity rather than building a BM25 index on every query. A pool that *does*
have a graph source fuses vector + BM25 + graph. Set `retriever_type` explicitly
(`vectorsimilarity`, `bm25`, `graph`, `rrf`) to override the default. The fusion
smoothing constant (`RRF_K = 60` in `src/config.py`) and the BM25 tokenizer
(`BM25_TOKENIZER = "jieba"`, or `"whitespace"` for space-delimited corpora;
switching it invalidates cached BM25 indexes) are set in `src/config.py`, not
per-request.

### Multiple vector sources and score scales

A pool can attach multiple vector sources. Retrieval queries each serving
vector source independently, takes up to `top_k` candidates per source and
interleaves the source result lists round-robin; it does not RRF-fuse unrelated
embedding-model rankings or globally sort them by raw score.
The text vector/BM25/graph fusion above stays within the document path.
ViCLIP and GME similarities are not calibrated, so one model can dominate
a mixed result. For separate rankings,
place the models in separate pools and make separate requests with
`asset_pool_ids: ["video-pool"]` and `asset_pool_ids: ["image-pool"]`.
`asset_pool_ids` filters pools, not sources. Returned metadata preserves the
producing `source_id` and the enclosing `pool_id`.

Retrieval and inference projection selection use `serving`, excluding
`PREPARING`, `DEGRADE` and disabled bindings. Document two-phase ingest
and OKF chunk lookup choose an accepting serving text projection, not a
multimodal projection. Formal agreement with main maintainers on multiple
vector sources (G19) and the serving-only selection rule (G20) is still needed
so later main changes keep these integration contracts; this is not an
acceptance statement.

### Multimodal retrieval and reranking

`target_media` accepts `document`, `image`, `video` and `audio`; omitted or empty
means all searchable sources. `document` selects text/table chunks; add `image`
for document figures. BM25/graph/RRF remain on the document path.

For a global ranking, set
`"postprocess":{"processor_type":"reranker","top_n":3}`. See
[Text-to-media retrieval](text-to-media-retrieval.md) for model selection,
response fields and failure behavior.

## Workspace

Everything written or loaded at runtime lives under `ENGINE_WORKSPACE` (default
`data-intelligence-engine/workspace`, `/workspace` in the container):

```text
workspace/
|-- milvus/
|   |-- etcd/
|   |-- minio/
|   `-- db/
|-- models/
|-- uploads/
|-- content/
|   `-- <library-id>/
|       |-- blobs/<sha256>
|       `-- assets/<asset-id>.json
`-- configs/
    |-- databases.json
    `-- asset_library.json
```

Treat `content/` and `configs/` as two halves of the same state. Library records
reference content objects, so back them up, restore them, and wipe them together.
Vector chunks live in Milvus and must be backed up with the corresponding
library state.

A service that uploads files for the engine shares `workspace/uploads` at the
same container path. It passes file paths to the engine, so both services must
resolve those paths identically.

## Console

The Data Intelligence Engine console is served at `/console/`; `/` redirects
there. It uses the REST API on the same origin and provides:

- A canvas: assets, pools and sources are dragged from an inventory onto a
  stage, where links show pool membership (asset → pool) and pool sources
  (pool → source). Drawing a link calls the API. New pools, sources and uploads
  start as drafts that are filled in on the inspector panel and then created.
  Node positions are kept per library in the browser's local storage.
- A Library tab whose left panel switches between libraries, assets, asset
  pools, sources, databases and models: asset listing and deletion (single or
  bulk), library, pool and source management
  (including attaching and detaching pool sources and adding assets to pools),
  database registration, editing, removal and connectivity checks, and
  embedding and reranking model availability.
- Asset upload from the browser: files or whole folders, picked or dropped.
- A Retrieve tab laid out as concept graph | retrieval and reranking |
  results: document retrieval by RRF, vector similarity, BM25 or graph, and
  document/image/video/audio modality selection from one pool or every pool in
  a library. Optional reranking includes the media default, and image and video
  hits are rendered inline.
- A concept graph of the selected pool (its OKF concepts and links). After an
  RRF or graph retrieval it highlights the seed concepts, the concepts reached
  at each hop, the links walked, and the concepts whose chunks are in the
  result; each result lists the concepts it came through.
- An English/Chinese switch and a light/dark theme, both remembered.

Source creation in both the Sources section and canvas inspector uses guided
controls, not an operator-options JSON editor. Choose the database first:

- Vector sources offer document/image/video/audio selection, model suggestions,
  backend and device dropdowns, local path overrides, and optional chunk/model
  tuning fields. Empty overrides inherit the engine's settings.
- Graph sources offer **OKF bundles only** or **Documents → OKF**. The latter
  exposes service URL, password-masked API key, request timeout, auto/manual/cron
  trigger controls, quiet period, and optional task language/goal/instructions.
  The console constructs the required nested extractor configuration for you.
- Object/SQL sources need no embedding or extractor fields.

Deleting a source also removes it from all pool bindings, including disabled or
unavailable copies and pending replacement references. Assets and external
collections are left untouched; a new source can be created and attached without
retaining the deleted ID. Queued extraction jobs for that source are cancelled.
Deletion returns `409` while an extraction is running: let publication finish
before removing its source. Content sources holding live assets remain protected.

The console is implemented in `ui/` and served by the engine from its built
`ui/dist/` output at `/console/`. Build it with `npm ci && npm run build` in
`data-intelligence-engine/ui`.

### Graph view and retrieval traces

`GET /v1/libraries/{library}/asset_pools/{pool}/graph` returns the pool's
persisted concept graph as `nodes` (`id`, `label`, `title`, `degree`) and
`edges` (`source`, `target`, `relation`). Above `ENGINE_GRAPH_VIEW_LIMIT`
concepts the best-connected ones are kept and `truncated` is true. A pool with
no graph source answers 404.

`POST /v1/retrieve` with `"include_graph_trace": true` adds `graph_traces`: for
each pool whose retrieval ran graph search (`graph`, or `rrf` on a pool with a
graph source), the `seeds`, every concept reached with its `hop` and `weight`,
the `edges` crossed, and per concept the `hit_chunk_ids` that made it into
`retrieved_chunks`.

## Configuration

Database connections are not environment settings. Register them through the
API and let the engine persist them in the workspace.

Only settings that differ between deployments are environment variables: where
the service listens and keeps its state, and which models it loads and on which
device, speech language/enabling, the optional video-summary service URL,
and the size limit of the console's graph view. They are read
at process startup; set them in
the shell for local runs, or in `deployment/docker/.env` for Compose, then
restart/recreate the engine. Invalid numeric values fail startup with the
offending variable name.

Everything else -- model properties (parsed from the model directory), the
layout model, OCR and BM25 tokenization, chunking, retrieval and rerank
defaults, RRF, graph-search weights, ingest batching, adapter timeouts and retries, CORS -- is a constant in
`src/config.py`. Most of these can be overridden where they are used: chunking
and figure context per source through `operator_options`, `top_k` and
`postprocess.top_n` per retrieval request, and graph-search weights through the
graph retriever's options.

| Variable | Default | Purpose |
|---|---|---|
| `ENGINE_HOST` | `0.0.0.0` | Bind address. |
| `ENGINE_PORT` | `16022` | Service port. |
| `ENGINE_LOG_LEVEL` | `INFO` | Level of the engine's own log lines, such as OKF extraction jobs being queued, started, finished or failed. |
| `ENGINE_WORKSPACE` | `data-intelligence-engine/workspace` | Root for uploads, content, configuration, bundled database state, and the default model directory. |
| `ENGINE_UPLOAD_DIR` | `$ENGINE_WORKSPACE/uploads` | Location used to resolve bare asset file names. |
| `ENGINE_MODEL_ROOT_PATH` | `$ENGINE_WORKSPACE/models` | Shared root for document, video, image, ASR, rerank, and layout models. An empty value also uses this default. |
| `ENGINE_DOC_EMBEDDING_BACKEND` | `local_openvino` | Document/fused embedding backend: `local_openvino` or `remote_openai_compatible`. The runtime (GME, GenAI, or LlamaIndex fallback) is chosen from the model. |
| `ENGINE_DOC_EMBEDDING_MODEL_ID` | `gme-Qwen2-VL-2B-Instruct-OV` | Document embedding model identifier; its final component names the local directory under the shared model root. |
| `ENGINE_DOC_EMBEDDING_DEVICE` | `CPU` | OpenVINO document embedding device. |
| `ENGINE_DOC_EMBEDDING_API_BASE` | empty | OpenAI-compatible document embedding endpoint. |
| `ENGINE_DOC_EMBEDDING_API_KEY` | `unused` | API key for the OpenAI-compatible document embedding endpoint. |
| `ENGINE_VIDEO_EMBEDDING_BACKEND` | `local_openvino` | Backend for prepared video packages. |
| `ENGINE_VIDEO_EMBEDDING_MODEL_ID` | `viclip-b-fp16` | Standalone video package ID; alternatives `viclip-l-fp16` and `cosmos-224p-fp16`, with fp32 variants for all three. |
| `ENGINE_VIDEO_EMBEDDING_DEVICE` | `CPU` | Video embedding device; set `GPU.0` explicitly for an Intel GPU. |
| `ENGINE_IMAGE_EMBEDDING_BACKEND` | `local_openvino` | Backend for standalone images and derived text. |
| `ENGINE_IMAGE_EMBEDDING_MODEL_ID` | `gme-Qwen2-VL-2B-Instruct-OV` | Image/transcript model: the directory name under the shared root. Vendor-style IDs such as `Alibaba-NLP/gme-*` are rejected. |
| `ENGINE_IMAGE_EMBEDDING_DEVICE` | `CPU` | Image and derived-text embedding device. |
| `ENGINE_ASR_MODEL_ID` | `whisper-small` | Speech-recognition model directory under the shared root; the backend is fixed to `local_openvino`. |
| `ENGINE_ASR_DEVICE` | `CPU` | Speech-recognition device. |
| `ENGINE_ASR_LANGUAGE` | `zh` | Whisper language; explicitly empty enables automatic detection. Compose preserves an empty value. |
| `ENGINE_ASR_ENABLED` | `true` | Enable background transcription (`1`, `true`, `yes` are true). |
| `ENGINE_VIDEO_SUMMARY_BASE_URL` | empty | Optional caption service; empty skips caption-task registration. |
| `ENGINE_LAYOUT_DEVICE` | `CPU` | Layout inference device. |
| `ENGINE_RERANK_BACKEND` | `local_openvino` | Backend for a text reranker such as `BAAI/bge-reranker-large`: `local_openvino` or `remote_openai_compatible`. |
| `ENGINE_RERANK_MODEL_ID` | `Qwen3-VL-Reranker-2B-INT8-OV` | Default reranker when a request sets no `postprocess.reranker_model`: a directory under the shared root. The Qwen3-VL default scores document text, figures, images, video and audio transcripts together; set a text reranker such as `BAAI/bge-reranker-large` to rerank document-only requests with it. |
| `ENGINE_RERANK_DEVICE` | `CPU` | OpenVINO reranker device. |
| `ENGINE_RERANK_API_BASE` | empty | Remote rerank endpoint for the `remote_openai_compatible` backend (vLLM, TEI, or any Cohere/Jina-style `/rerank`); `/rerank` is appended unless already present. |
| `ENGINE_RERANK_API_KEY` | `unused` | API key sent as `Authorization: Bearer` to the remote rerank endpoint. |
| `ENGINE_MEDIA_RERANK_BACKEND` | `local_openvino` | Media reranker backend; `local_openvino` is the only supported value. |
| `ENGINE_MEDIA_RERANK_MODEL_ID` | `Qwen3-VL-Reranker-2B-INT8-OV` | Multimodal reranker for text, image, video and audio-transcript candidates: the Qwen3-VL IR package directory under the shared model root (FP16: `Qwen3-VL-Reranker-2B-OV`). |
| `ENGINE_MEDIA_RERANK_DEVICE` | `GPU` | OpenVINO device for media reranking. |
| `ENGINE_MEDIA_RERANK_DOC_WORKERS` | `8` | Workers loading candidate media before reranking (maximum 32). |
| `MEDIA_RERANK_VIDEO_MAX_FRAMES` | `8` | Frames sampled per video candidate during media reranking. |
| `ENGINE_GRAPH_VIEW_LIMIT` | `1500` | Most concepts `GET /v1/libraries/{library}/asset_pools/{pool}/graph` returns for drawing; beyond it the best-connected concepts are kept and the response is marked `truncated`. |

For explicit media requests and a response-checking script, see
[text-to-media-retrieval.md](text-to-media-retrieval.md). See
[Multimodal retrieval and reranking](#multimodal-retrieval-and-reranking) for
modality selection, automatic reranker routing and fallback behavior.

An unset or empty `HF_ENDPOINT` uses the mirror. Both local runs and Compose
preserve an explicit nonempty override. This changes the metadata/download
endpoint; it does not enable offline mode.

All local models must be downloaded and exported before engine startup. The
engine loads local artifacts only; it neither configures a model-download
endpoint nor downloads or exports missing models. Remote inference providers
still call their configured APIs, without downloading a local model.

The defaults above are `src/config.py`'s. `deployment/docker/docker-compose.yml`
spells out a default for every variable as `${VAR:-default}`; it matches these
except that the Compose deployment defaults document embedding and reranking
devices to `GPU`, and the workspace to `/workspace`.

Document embedding deployment settings use `ENGINE_DOC_EMBEDDING_*`. Update
existing `.env` files to those names. Individual model-path environment settings
are no longer read: set `ENGINE_MODEL_ROOT_PATH` to the parent directory holding
the model folders instead, not to a single checkpoint or exported package.
Each source can select a prepared model with `operator_options.embedding_model`.
A model root outside the container's workspace must also be mounted
into the container at that path.

When a request omits `top_k` or postprocessing `top_n`, it uses
`RETRIEVE_TOP_K` / `RERANK_TOP_N` from `src/config.py` (`5` / `3`). Explicit
request values take precedence.

Multimodal tuning is also in `src/config.py`, **not environment variables**:

| Constant | Value | Purpose |
|---|---|---|
| `SHORT_VIDEO_MAX_SECONDS` | `60.0` | Whole-clip embedding cutoff; longer video needs segmentation, not yet implemented. |
| `BACKFILL_BATCH_SIZE` | `32` | Assets per catch-up write for a newly attached source. |
| `ASR_SEGMENT_SECONDS` | `30.0` | Maximum transcript-block duration, split near pauses. |
| `ASR_PROMPT` | Mandarin prompt for `zh`, otherwise empty | Script/punctuation hint derived from `ASR_LANGUAGE`. |
| `VIDEO_SUMMARY_TASK` | `summary` | Caption-service task. |
| `VIDEO_SUMMARY_TIMEOUT` | `300.0` | Caption-service timeout in seconds. |

Former `ENGINE_*` spellings for these constants are no longer read. There is
no ASR or layout backend environment knob either; both are fixed to `local_openvino`.
The deployment configuration test compares every environment setting read by
the engine with Compose forwarding and requires its exact name in this guide.

### Compose deployment

Every variable below has a Compose default. Put only the ones a deployment
changes in `deployment/docker/.env`, which Compose reads automatically. Do not
commit `.env` or production credentials. Existing deployment files do not need
to be overwritten.

| Variable | Default | Purpose |
|---|---|---|
| `ENGINE_PORT` | `16022` | Published host port in Compose; the local Python process uses it as its listener port. |
| `ENGINE_CONTAINER_PORT` | `16022` | Container listener, port-mapping target, and healthcheck port. |
| `ENGINE_WORKSPACE_PATH` | `../../workspace` | Host bind-mount source, relative to the Compose directory. |
| `ENGINE_WORKSPACE` | `/workspace` | Container bind-mount target; derived model paths follow it. |
| `ENGINE_NETWORK` | `data-intelligence-network` | Shared external network for all three stacks. |
| `ENGINE_IMAGE` | `data-intelligence-engine:latest` | Engine image reference. |
| `ENGINE_GPU_DEVICE` | `/dev/dri` | Host GPU device path passed through to the same container path. |
| `VIDEOGROUPID`, `RENDERGROUPID` | `44`, `992` | GPU group IDs; discover the actual values on the deployment host. |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | `minioadmin` | Shared MinIO server and Milvus client credentials. Change both before production use. |
| `MINIO_UID`, `MINIO_GID` | `65532` | MinIO process identity. The one-shot `minio-init` service chowns the bind-mounted data directory to it before MinIO starts, so it need not exist on the host. |
| `MINIO_INIT_IMAGE` | `$MILVUS_IMAGE` | Image for `minio-init`; needs `sh`, `find`, and `chown`, and runs as root. |
| `MINIO_API_PORT`, `MINIO_CONSOLE_PORT` | `9000`, `9001` | Internal MinIO listeners. The API port also updates Milvus's endpoint and the MinIO healthcheck. |
| `MILVUS_PORT` | `19530` | Published Milvus client port; internal client port remains 19530. |
| `MILVUS_ETCD_ENDPOINTS` | `etcd:$ETCD_CLIENT_PORT` | Optional override for the Milvus etcd endpoint. |
| `MILVUS_MINIO_ADDRESS` | `minio:$MINIO_API_PORT` | Optional override for the Milvus object-store endpoint. |
| `ETCD_CLIENT_PORT` | `2379` | etcd listener, advertised endpoint, and healthcheck port. |
| `ETCD_AUTO_COMPACTION_MODE` | `revision` | etcd automatic-compaction mode. |
| `ETCD_AUTO_COMPACTION_RETENTION` | `1000` | etcd compaction retention. |
| `ETCD_QUOTA_BACKEND_BYTES` | `4294967296` | etcd storage quota. |
| `ETCD_SNAPSHOT_COUNT` | `50000` | etcd snapshot interval. |
| `NEBULA_IMAGE_REGISTRY`, `NEBULA_VERSION` | `docker.io/vesoft`, `v3.6.0` | Common Nebula image registry and version. |
| `NEBULA_USERNAME`, `NEBULA_PASSWORD` | `root`, `nebula` | Credentials for the storage-initialization client, not server password rotation. Set matching credentials in graph registrations separately. |
| `NEBULA_NOFILE_LIMIT` | `65535` | Shared Nebula soft/hard file-descriptor limit. |
| `NEBULA_LOG_VERBOSITY`, `NEBULA_MIN_LOG_LEVEL` | `0` | Nebula logging settings. |

`ETCD_IMAGE`, `MINIO_IMAGE`, and `MILVUS_IMAGE` can replace the pinned image
references in the Compose file. Project and container names can also be
overridden with the corresponding `*_COMPOSE_PROJECT` / `*_CONTAINER_NAME`
variables. `ENGINE_NO_PROXY` replaces the shared service/private-network bypass
list; keep all required service names when customizing it.

The Nebula `NEBULA_{META,STORAGE,GRAPH}_PORT` and `*_HTTP_PORT` settings publish
host ports; `NEBULA_{META,STORAGE,GRAPH}_INTERNAL_PORT` and
`*_INTERNAL_HTTP_PORT` change listeners and their dependent commands/healthchecks.
If an internal client port changes, update database registration URLs as well.

Healthcheck interval, timeout, retries, and startup grace periods use the
`ENGINE_HEALTHCHECK_*`, `MILVUS_HEALTHCHECK_*`, and `NEBULA_HEALTHCHECK_*`
variables, with the existing Compose defaults retained. MinIO readiness uses an
anonymous local health endpoint, so custom credentials do not have to be
embedded in a URL.

Engine settings from [Configuration](#configuration) go in the same `.env`, for
example:

```dotenv
ENGINE_DOC_EMBEDDING_DEVICE=CPU
ENGINE_RERANK_DEVICE=CPU
```

Export PP-DocLayoutV3 once before starting the engine:

```bash
PYTHONPATH=src python scripts/export_pp_doclayout_v3.py
```

The converter needs a Transformers version with PP-DocLayoutV3 support
(verified with 5.5.4) and ONNX. It can run in an isolated environment because
normal OpenVINO inference uses PIL/NumPy preprocessing and does not import that
newer Transformers version.

Compose overrides several model defaults for GPU deployment. Check
`deployment/docker/docker-compose.yml` when debugging a container value.

### Remote document embedding

The `remote_openai_compatible` backend sends document and query text to an
OpenAI-compatible embedding server instead of loading a model in the engine
process. GME served by the
[multimodal-embedding-serving](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/multimodal-embedding-serving)
microservice (model `GME/gme-qwen2-vl-2b-instruct`) is one such server. Any
server that implements `POST /v1/embeddings` also works.

Start the serving container with GME as described in its get-started guide,
then check that the endpoint answers **from inside the engine container**.
`HOST_IP` is the serving host's IP. The first IP address works when the server
runs on this host:

```bash
HOST_IP=$(hostname -I | awk '{print $1}')
docker exec data-intelligence-engine curl -s "http://$HOST_IP:9777/v1/embeddings" \
  -H 'Content-Type: application/json' \
  -d '{"model":"GME/gme-qwen2-vl-2b-instruct","input":["hello"]}' | head -c 200
```

`localhost` inside the engine container is the engine itself. Use the serving
host's IP address, or attach both containers to the same Docker network and use
the serving container's name. If proxies are injected into the containers, add
that host to `ENGINE_NO_PROXY`. The default list covers `172.16.0.0/12` and
`192.168.0.0/16` but not `10.0.0.0/8`.

To make the remote model the engine-wide default, add the following to
`deployment/docker/.env` and recreate the engine (`docker compose up -d`):

```bash
cat >> deployment/docker/.env <<EOF
ENGINE_DOC_EMBEDDING_BACKEND=remote_openai_compatible
ENGINE_DOC_EMBEDDING_MODEL_ID=GME/gme-qwen2-vl-2b-instruct
ENGINE_DOC_EMBEDDING_API_BASE=http://$HOST_IP:9777
EOF
```

`ENGINE_DOC_EMBEDDING_API_BASE` is the server root. The engine appends `/v1`
when it is missing, and the client then calls `<api_base>/v1/embeddings`.
`ENGINE_DOC_EMBEDDING_MODEL_ID` is sent as the request's `model`; here it is
just the remote model name (`GME/gme-qwen2-vl-2b-instruct`). Image and video
media sources cannot use the remote backend. The
microservice does not check `ENGINE_DOC_EMBEDDING_API_KEY`, so leave it
`unused`. `ENGINE_DOC_EMBEDDING_DEVICE` is ignored, because the device is chosen
on the serving side.

To use the remote model for a single vector source instead, pass the provider
in that source's `operator_options` when you register it. The engine-wide
defaults stay as they are:

```bash
curl -X POST "$ENGINE_URL/v1/libraries/<library>/sources" \
  -H 'Content-Type: application/json' \
  -d '{"name":"vec-remote","database_id":"<milvus-id>","collection_name":"remote_vectors",
       "operator_options":{"embedding_backend":"remote_openai_compatible",
                           "embedding_model":"GME/gme-qwen2-vl-2b-instruct",
                           "embedding_api_base":"http://'"$HOST_IP"':9777"}}'
```

The API key is always read from `ENGINE_DOC_EMBEDDING_API_KEY`. There is no
per-source key.

The engine needs `llama-index-embeddings-openai`, which `pyproject.toml`
declares. An image built before that dependency was added fails with
`No module named 'llama_index.embeddings.openai'` when a remote source is
attached. Rebuild the image to fix it.

Behaviour to be aware of:

- **Dimension.** When a pool attaches the source, the engine embeds a probe text
  and sizes the collection from the result: 1536 for GME. An existing
  collection must already have that dimension.
- **Frozen profile.** A source records its provider and model when it is
  created. Changing the `ENGINE_DOC_EMBEDDING_*` defaults later does not move
  existing sources to the remote model, so register a new source and
  re-ingest. The endpoint is not part of the profile, though: if the API base
  changes, an existing remote source sends its requests to the new address.
  Point it only at a server that runs the same model.
- **Same vectors as local GME.** With the same INT8 package, the serving
  microservice's `/v1/embeddings` returns the same vectors as the
  local GME runtime (`local_openvino`), for both queries and documents.
- **Text only.** The OpenAI protocol carries text, so a remote model is not a
  fused image+text embedder. Figure nodes are embedded from their caption and
  surrounding text instead of from caption plus pixels. Use
  `local_openvino` with a GME package when figure retrieval by image content matters.
- **Scope.** Only document embedding goes remote. Standalone image, video, and
  speech sources keep their local `ENGINE_IMAGE_EMBEDDING_*`,
  `ENGINE_VIDEO_EMBEDDING_*`, and `ENGINE_ASR_*` models. Reranking has its own
  remote settings, `ENGINE_RERANK_BACKEND=remote_openai_compatible` and
  `ENGINE_RERANK_API_BASE`.

## Models

Local OpenVINO models live under `$ENGINE_MODEL_ROOT_PATH`, which defaults to
`$ENGINE_WORKSPACE/models`. Document, video, image, speech, rerank, and layout
models share this root, and `/v1/models` scans it for available models. Sources
select a prepared model with `operator_options.embedding_model`; model directories
are derived from their configured IDs. Missing or incomplete models fail with a clear
preparation error rather than being downloaded or exported on first use.
Model discovery is exposed through `/v1/models` for UI selectors and
other clients.

The Console lists all model types, highlights embedding defaults by asset type and shows inherited values in source forms. See [Models API](api.md#models) for response fields.

Weight variants are separate prepared model IDs/directories under that root.
Select one with `operator_options.embedding_model`. Export tools choose weight
precision during offline preparation, and model-package metadata determines
which artifacts are loaded.

Video defaults to `viclip-b-fp16`; optional models are `viclip-l-fp16` and `cosmos-224p-fp16`, with `-fp32` variants available. Select one through `operator_options.embedding_model`; use separate collections for different models.

Prepare the complete artifact set for each capability before starting the engine:

- Text embeddings and rerankers: `openvino_model.xml` / `.bin`, model config,
  and tokenizer files. GenAI additionally needs its exported tokenizer IR.
- ViCLIP and Cosmos: `video_embedding.json`, video/text XML and BIN pairs, and tokenizer files.
- GME: its prepared package config, language/visual XML and BIN pairs, processor,
  and tokenizer files.
- Qwen3-VL reranker: `reranker_text`, `reranker_image` and `reranker_video`
  XML/BIN pairs, `export_shapes.json`, and processor files.
- Whisper: exported encoder/decoder XML and BIN pairs, config, processor, and
  tokenizer files, directly in its directory or under `openvino/`.
- PP-DocLayoutV3: the ONNX artifact and metadata produced by the standalone
  layout-export script above (or a local checkpoint for the explicit torch path).

The [preparation guide](how-to-guides/how-to-prepare-models.md)
contains standalone download/export examples. The model-discovery `ready` flag
reports local inference artifacts; `false` requires external preparation, not a
slow first-use export.

Chunk token counting also requires the local `cl100k_base` vocabulary cache
normally bundled with LlamaIndex. If that cache is missing or corrupt, prepare
it outside the engine rather than relying on an automatic fetch. Sentence
splitting uses Punkt directly and does not invoke NLTK's resource downloader.

There are two model backends for embedding and text reranking:

- `local_openvino`: run an OpenVINO model from the shared model root. The
  runtime is chosen internally from the model: OpenVINO GenAI for standard IR
  text embedding/rerank (with a LlamaIndex fallback), the GME runtime for GME
  packages, OpenVINO Core for ViCLIP, Cosmos, VL reranking and layout, and
  Optimum for ASR. It is recorded as `runtime` in source profiles and is not
  configurable.
- `remote_openai_compatible`: call an OpenAI-compatible HTTP endpoint.

The former names `llamaindex_openvino`, `openvino_genai`, `native_openvino_gme`,
`openai_compatible` and `openvino_vl` are no longer accepted.

Media reranking is `local_openvino` only (`ENGINE_MEDIA_RERANK_*`); a media
reranker is recognized as a Qwen3-VL export. It is not a valid embedding
backend.

A GME package under `local_openvino` is the document/text-and-figure model; a
standard IR directory such as BGE uses the same backend. Document sources
using GME are not interchangeable with standalone-media sources.

Model discovery lists GME, ViCLIP and Cosmos under `embedding`, and Whisper under `asr`. Qwen3-VL reranker packages appear under `reranker` with `media: true`, and `/v1/models/reranker` reports the configured media default as `media_model_id`.

The project pins its OpenVINO and transformer stack in `pyproject.toml`. The
PyTorch CPU wheel index is required during installation because the project pins
`torch` and `torchvision` with `+cpu` versions.

## Operations

- Older Milvus data may live under `data-intelligence-engine/volumes/{etcd,minio,milvus}`. Move it
  into `data-intelligence-engine/workspace/milvus/{etcd,minio,db}` before starting the new Compose
  layout.
- Milvus containers may write `workspace/milvus/*` as root. Engine-owned
  `configs/`, `uploads/`, and `content/` must remain writable by the engine
  container user.
- Inter-container traffic must bypass injected HTTP proxies. The supplied
  Compose files set `no_proxy` for service hostnames and private networks.
- The Docker build context must be the `data-intelligence-engine/` project root.
- Builds require Docker BuildKit (the default with current Docker Compose).
  Dependencies are installed in a layer keyed by `pyproject.toml`, before the
  source is copied, so code-only rebuilds reuse the installed packages; the
  engine itself is then installed without dependency resolution, build
  isolation or index access. BuildKit keeps pip's download cache outside the
  image, and Compose embeds inline cache metadata in each image and imports it
  as a cache source, so on a new builder pull a previously built image first to
  reuse its layers. The optional OKF extractor builds the same way from its
  `requirements.txt`. Avoid `--no-cache` and build-cache pruning for routine
  rebuilds.

### When attaching a source fails

Attaching a source to a pool is the first operation that dials a backend and
loads the embedding model, so it is where a deployment problem usually surfaces
— as a `503` from `PUT /v1/libraries/{library}/asset_pools/{pool}/sources`.
Two common causes, both reported in the response body:

- `MilvusException: Fail connecting to server on ...` — the engine cannot
  resolve or reach Milvus. Check they share a network:

  ```bash
  docker network inspect data-intelligence-network -f '{{range .Containers}}{{.Name}} {{end}}'
  ```

  Both containers should be listed. A Milvus stack started by another compose
  project joins that project's network instead, and
  `docker network connect data-intelligence-network milvus-standalone`
  attaches it without a restart — until it is recreated, so prefer bringing it
  up from `docker-compose-milvus.yml`.
- `[GPU] Can't get PERFORMANCE_HINT property as no supported devices found` —
  the devices are passed through but not readable, which means the
  `VIDEOGROUPID`/`RENDERGROUPID` group IDs in `.env` are absent or wrong.
  Confirm with:

  ```bash
  docker exec data-intelligence-engine python3 -c \
    "import openvino as ov; print(ov.Core().available_devices)"
  ```

  A GPU-capable host should report `GPU` and not just `['CPU']`. Fix `.env`
  and run `docker compose up -d` to recreate the container. Setting
  `ENGINE_DOC_EMBEDDING_DEVICE=CPU` and `ENGINE_RERANK_DEVICE=CPU` is the
  fallback if the host has no usable GPU.

## Source Map

```text
src/api/          FastAPI route handlers
src/assetlib/     assets, sources, pools, synchronization, and content contracts
src/core/         extraction, indexing, retrieval, models, and persistence
src/databasehub/  database registrations and backend adapters
ui/               Vue management console, served from the built ui/dist/
src/main.py       service entrypoint
```

Core parsing, indexing, retrieval, postprocessing, and model integration were
adapted from EdgeCraftRAG. The engine-specific layers add asset-library
ownership, runtime database registration, source reconciliation, and workspace
persistence.
