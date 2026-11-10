# Data Intelligence Engine API

The engine exposes a FastAPI JSON API on port `16022` by default. The base URL
for local development is `http://localhost:16022`.

- OpenAPI schema: `GET /openapi.json`
- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`

For concepts and operational guidance, see the [user guide](user-guide.md).

## Conventions

- Request and response bodies use JSON.
- `{library}` accepts either an asset-library name or ID.
- Every asset operation names its library; there is no implicit active library.
- Invalid input returns `400`, missing resources return `404`, conflicts return
  `409`, and unavailable source backends return `503` where applicable.
- Endpoints that attach assets or sources may schedule synchronization as a
  background task. Inspect the pool's `source_statuses` for progress and errors.

## System

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Redirect to the console. |
| `GET` | `/health` | Return liveness, workspace path, and database/library counts. |

## Asset Libraries

All routes in this section use the `/v1/libraries` prefix.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | List asset libraries. |
| `POST` | `/` | Create an asset library. |
| `GET` | `/{library}` | Get one library by name or ID. |
| `PATCH` | `/{library}` | Update its description, or where new content goes. |
| `DELETE` | `/{library}` | Delete the library. |
| `GET` | `/{library}/sources` | List registered sources, content included. |
| `POST` | `/{library}/sources` | Register a source backed by a database collection. |
| `PATCH` | `/{library}/sources/{source_id}` | Change a source's `name`, `labels` or `enabled` switch. Its model and parameters cannot change (`422`): create a new source and attach it with `replaces`. |
| `DELETE` | `/{library}/sources/{source_id}` | Detach a source from every pool without deleting its external collection. Cancel queued extraction jobs. Refused with `409` while it holds live asset content or has a running OKF extraction. |
| `GET` | `/{library}/asset_pools` | List asset pools. |
| `POST` | `/{library}/asset_pools` | Create an asset pool, optionally with sources. |
| `GET` | `/{library}/asset_pools/{asset_pool_id}` | Get one asset pool. |
| `DELETE` | `/{library}/asset_pools/{asset_pool_id}` | Delete an asset pool and its internal projections. |
| `GET` | `/{library}/asset_pools/{asset_pool_id}/sources` | List sources attached to a pool. |
| `PUT` | `/{library}/asset_pools/{asset_pool_id}/sources` | Replace the sources attached to a pool. An entry may be `{"source_id": ..., "replaces": ...}` to have that source take over from another once it has caught up. |
| `PATCH` | `/{library}/asset_pools/{asset_pool_id}/sources/{source_id}` | Set this binding to `{"serving_state":"DEGRADE"}` or resume it with `{"serving_state":"SERVING"}`. Returns the pool's actual states; a resumed source behind the pool reports `PREPARING` until ready. |
| `GET` | `/{library}/asset_pools/{asset_pool_id}/routing` | Which source takes each kind of content in the pool, and in which serving state. |
| `GET` | `/{library}/asset_pools/{asset_pool_id}/assets` | List asset IDs held by a pool. |
| `POST` | `/{library}/asset_pools/{asset_pool_id}/assets` | Add existing library assets to a pool. |
| `GET` | `/{library}/asset_pools/{asset_pool_id}/graph` | Read the OKF concept graph (`nodes`, `edges`, `total`, `truncated`); optional `limit`. Each node's `origin` is `uploaded`, `generated` or `both` (an uploaded override). |
| `POST` | `/{library}/asset_pools/{asset_pool_id}/extractions` | Extract the pool's documents into OKF for a graph source (`{"source_id"?, "force"?}`). 202 with a new job; 200 with the active one. |
| `GET` | `/{library}/asset_pools/{asset_pool_id}/extractions[/{extraction_id}]` | Extraction jobs (newest first) or one job: `state` (`queued`, `running`, `succeeded`, `failed`, `cancelled`), `result`, `error`. |
| `DELETE` | `/{library}/asset_pools/{asset_pool_id}/extractions/{extraction_id}` | Cancel a queued job; 409 for a running one. |
| `GET` | `/{library}/assets?page_num=1&page_size=20` | List stored file and inline-text assets. |
| `GET` | `/{library}/assets/{asset_id}/enrichment` | Read media caption, transcript and embedding coverage states after background extraction. |
| `PUT` | `/{library}/uploads/{path}` | Stage raw file bytes, returning `name`, `file_path`, `size` and `supported`; does not ingest. |
| `DELETE` | `/{library}/assets` | Delete several assets by ID from the library and every pool. |
| `DELETE` | `/{library}/assets/{asset_id}` | Delete one asset from the library and every pool. |

Create a library:

```bash
curl -X POST http://localhost:16022/v1/libraries \
  -H 'Content-Type: application/json' \
  -d '{"name":"manuals","description":"Product manuals","content_database":"local-content"}'
```

### Where asset content goes

A library's content lives in a registered **source** like everything else — an
object source, listed by `GET /{library}/sources` beside the vector and graph
ones. `default_content_source_id` on the library says which one new content goes
to, and `content_database` reports that source's database.

`content_database` on create is shorthand: it registers the content source in
that object database. Omit it and the library resolves one on first ingest —
the sole registered object database if there is exactly one, and otherwise the
engine's own workspace store (`$ENGINE_WORKSPACE/content`, registered on demand
as `workspace-content`). So ingesting content never fails for want of somewhere
to put it, and a deployment with several object stores is asked rather than
guessed at.

Equivalently, register the source yourself and point the library at it:

```bash
curl -X POST http://localhost:16022/v1/libraries/manuals/sources \
  -H 'Content-Type: application/json' \
  -d '{"name":"content","database_id":"local-content","collection_name":"manuals"}'

curl -X PATCH http://localhost:16022/v1/libraries/manuals \
  -H 'Content-Type: application/json' \
  -d '{"default_content_source_id":"<source-id>"}'
```

Moving that pointer changes where the *next* asset goes and nothing else: every
asset records the source its content was written to and keeps reading from it,
so a library may hold content in several stores at once. That is also why
detaching a source that still holds content is refused — its assets read through
it.

Register a vector source and create a pool:

```bash
curl -X POST http://localhost:16022/v1/libraries/manuals/sources \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"manual-vectors",
    "database_id":"local-milvus",
    "collection_name":"manual_vectors",
    "operator_options":{}
  }'

curl -X POST http://localhost:16022/v1/libraries/manuals/asset_pools \
  -H 'Content-Type: application/json' \
  -d '{"id":"all-manuals","name":"All manuals","sources":["<source-id>"]}'
```

## Databases

All routes in this section use the `/v1/databases` prefix.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | List registered database connections. |
| `POST` | `/` | Register a database connection. |
| `GET` | `/backends` | List supported database types and backends. |
| `GET` | `/{database_id}` | Get a registration; credentials are masked. |
| `PATCH` | `/{database_id}` | Update backend options or description. The type cannot change. |
| `DELETE` | `/{database_id}` | Delete an unused registration. |
| `POST` | `/{database_id}/check` | Test connectivity and return `reachable` plus any error. |

The engine connects to no database at startup. Registrations are runtime state,
persisted in `workspace/configs/databases.json`, and restored before asset
libraries. The one registration the engine makes for itself is
`workspace-content`, a filesystem object store under the workspace, written down
the first time a library needs somewhere to put asset content and has not been
told where. It is an ordinary registration: listed here, checkable, and
deletable once nothing points at it.

Registering does not connect immediately. Use the check endpoint to test the
backend. Returned credentials are masked, but a masked value sent back in a
patch preserves the stored secret. Deleting a registration still used by a
source or content store returns `409` and lists its users.

```bash
curl -X POST http://localhost:16022/v1/databases \
  -H 'Content-Type: application/json' \
  -d '{
    "id":"local-milvus",
    "type":"vector",
    "backend":"milvus",
    "options":{"uri":"http://localhost:19530"}
  }'

curl -X POST http://localhost:16022/v1/databases/local-milvus/check
```

A library referencing a database that is missing at restore time is retained.
Its source reports `reconciled: false`, and its pool source status reports the
failure until the database is registered and the source is reattached or the
service restarts.

## Assets

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/libraries/{library}/assets` | Store files and/or inline text as assets, optionally indexing them through selected pools. |

A bare file name is resolved under `$ENGINE_UPLOAD_DIR`; absolute paths are used
as supplied. One file creates one asset even when extraction yields many blocks.
Set `asset_pool_ids` to index the assets in those pools. With an empty list, the
assets are stored in the library but are not searchable. The endpoint returns
`202 Accepted` with `status: "materializing"` before background extraction,
storage, registration and indexing finish. `stored` remains a schema value
for already-stored content; `indexing` is not an ingest response status.
The response has no `warnings` field: media coverage cannot be known before
extraction. Poll `GET /{library}/assets` for all returned IDs and their
`materialization` (`materializing`, `text_ready`, `ready`). A missing ID just
after acceptance can mean extraction has not registered it yet. A phase may
be `null` after restart because this progress tracker is process-local.

`content_source_id` puts this batch's content in one of the library's object
sources instead of the default — an archival store for a bulk import, say. It is
reported back on the response, and on each asset from
`GET /{library}/assets`. Re-ingesting a file names the same asset, so sending it
with a different `content_source_id` moves that asset's content and discards the
previous record.

```bash
curl -X POST http://localhost:16022/v1/libraries/manuals/assets \
  -H 'Content-Type: application/json' \
  -d '{
    "asset_pool_ids":["all-manuals"],
    "file_paths":["guide.pdf"],
    "text":"Optional inline content"
  }'
```

Example response:

```json
{
  "library": "manuals",
  "asset_ids": ["<asset-id>"],
  "asset_pool_ids": ["all-manuals"],
  "file_paths": ["/workspace/uploads/guide.pdf"],
  "content_source_id": "<source-id>",
  "status": "materializing"
}
```

After extraction, query `GET /{library}/assets/{asset_id}/enrichment` for
`embedding_status` and `embedding_reason`. `no_source` means no configured
serving source can embed that media; `unassigned` means no pool assignment.
Other states are `not_applicable`, `pending`, `ready`, and `failed`.
`caption_status` and `transcript_status` independently report `pending`,
`completed`, `failed`, or `skipped`; audio also reports `transcript_segments`
and `transcript_error`. With no `ENGINE_VIDEO_SUMMARY_BASE_URL`, captioning
is `skipped` with a reason in `error`. Background jobs are registered after
extraction and run after initial pool sync (captions, then transcription).
`materialization: "ready"` and a ready pool do not imply those jobs finished;
wait for `transcript_status: "completed"` plus `embedding_status: "ready"`
before treating audio transcripts as searchable.

Re-adding a file with the same origin updates its stable asset ID. Pools that
already contain that asset are re-indexed even when they are not repeated in
`asset_pool_ids`.

To index assets that are already stored in the library, use `POST
/v1/libraries/{library}/asset_pools/{asset_pool_id}/assets` with an `asset_ids`
array. That endpoint changes pool membership; it does not upload or extract
content again.

Asset deletion removes materializations from every pool containing the target,
then deletes its content record and library membership. It returns `409`
without changing the library when an attached source is unavailable or does not
support per-asset removal. Binary blobs are content-addressed and are reclaimed
separately, because another asset may still reference the same blob.
Standalone media uses `file://` references rather than a second blob copy.
Deletion returns `files_removed` for engine-owned media inside the upload
directory and `files_kept` for external files, which the engine never deletes.

Document illustrations (`role: "doc_image"`) normally use the document
source's GME fused image/reference-text path. A source explicitly configured
with the `local_openvino` GME document package has a `text` profile, not a multimodal indexer.
Only explicit user co-location of a GME multimodal source accepting those
images with the document source indexes an illustration in both sources;
use separate pools or source filters to avoid that choice.

## Retrieval

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/retrieve` | Retrieve across libraries and optionally postprocess the merged chunks. |

An empty `asset_pool_ids` list searches all vector-capable pools in the named
libraries. Omit `postprocess` to return retrieval results without reranking.
Omitted `top_k` defaults to `5`, and omitted `postprocess.top_n` to `3`
(`RETRIEVE_TOP_K` / `RERANK_TOP_N` in `src/config.py`).
`target_media` scopes the search by modality: empty searches every searchable
source; an explicit list searches those modalities only. `document` retrieves
text only — select `image` alongside it to also search the figures inside
documents. Images are identified by their `metadata.kind == "image"`.

```bash
curl -X POST http://localhost:16022/v1/retrieve \
  -H 'Content-Type: application/json' \
  -d '{
    "query":"How do I reset the device?",
    "libraries":["manuals"],
    "asset_pool_ids":[],
    "top_k":5,
    "target_media":["document"],
    "postprocess":{"processor_type":"reranker","top_n":3}
  }'
```

Each pool answers from its serving sources only: a source still catching up,
deprecated or disabled is not queried.
A chunk's `metadata.source_id` names the source that produced it and
`metadata.pool_id` the pool it was retrieved through.

All serving vector sources in a pool are queried independently. Each source
contributes up to `top_k` candidates and the source result lists are interleaved
round-robin, not RRF-fused or globally sorted by raw score across embedding
models. ViCLIP and GME similarities are not calibrated, so their raw scores
cannot establish a global order. Issue separate requests with
`asset_pool_ids: ["video-pool"]` and `asset_pool_ids: ["image-pool"]` for
separate rankings. `asset_pool_ids` filters pools, not individual sources;
sources that need separate rankings must be placed in separate pools.
`retriever_type` (`rrf`, `vectorsimilarity`, `bm25`, `graph`) still controls
the text vector/BM25/graph path; multimodal sources use vector similarity.
`include_graph_trace: true` adds `graph_traces` for graph/RRF traversal,
including document queries scoped by `target_media` or `exclude_chunk_ids`.
The trace comes from the same retrieval; enabling it does not run a second graph search.

`retrieved_chunks` contains the merged retrieval result before postprocessing;
`chunks` contains the final result. `postprocess.query` may override the search
query for reranking, and `exclude_chunk_ids` removes previously seen chunks
before postprocessing. A `target_media` without `image` excludes images inside
the retrieval queries, so excluded images do not consume `top_k` slots.

Without `postprocess.reranker_model`, the default reranker
`Qwen3-VL-Reranker-2B-INT8-OV` (`ENGINE_RERANK_MODEL_ID`) scores text and media
candidates together. `postprocess.reranker_model` selects the reranker per
request; unset fields fall back to the `ENGINE_RERANK_*` settings. To rerank on a remote server (vLLM, TEI,
or another `/rerank` endpoint) for one request only:

```json
"postprocess":{"processor_type":"reranker","top_n":3,
  "reranker_model":{"backend":"remote_openai_compatible",
                    "model_id":"BAAI/bge-reranker-large",
                    "api_base":"http://reranker:8000/v1"}}
```

### Media bytes

`GET /v1/blob` accepts `library`, `source_id` and `media_key` query parameters
from a retrieved chunk. It serves content-store blobs and registered
`file://` media references. An arbitrary unregistered filesystem path must
not be readable through this route.

## Models

All routes in this section use the `/v1/models` prefix.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Return `embedding`, `reranker`, `layout` and `asr` options. |
| `GET` | `/devices` | List available OpenVINO devices plus `AUTO`. |
| `GET` | `/{model_type}` | Return options for one model type. `multimodal` is a compatibility view of media-capable embeddings. |
| `GET` | `/{model_type}/names` | Return only the available model names. |

Models are discovered under `$ENGINE_MODEL_ROOT_PATH` (default `$ENGINE_WORKSPACE/models`). Text and multimodal models share `embedding`; Whisper uses `asr`.

- Embedding `supported_asset_types`: supported default representations; audio may use transcripts, but video captions alone do not count as video support.
- Embedding `defaults`: per-asset `backend`, `model_id`, `model_path`, `device`, `api_base`, keyed by `document`, `image`, `video`, `audio`.
- Console highlights default models; source forms display inherited values without saving them as overrides.

See the [user guide](user-guide.md#models) for model and device configuration.

### Embedding backends

Backend names are `local_openvino` and `remote_openai_compatible`; the former
names (`llamaindex_openvino`, `openvino_genai`, `native_openvino_gme`,
`openai_compatible`) are rejected. The runtime (GenAI or LlamaIndex for standard
IR text models, GME, or OpenVINO Core for ViCLIP and Cosmos) is chosen
internally from the model and recorded as `runtime` in the source profile. A
GME package under `local_openvino` selected for a document source gives the
document/text-and-figure profile, not a standalone-media source.
