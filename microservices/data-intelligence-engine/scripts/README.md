<!-- Copyright (C) 2025 Intel Corporation
     SPDX-License-Identifier: Apache-2.0 -->

# Engine API helpers

The shell helpers are thin wrappers around the engine's HTTP API. Each invocation
makes one request, writes the response body to stdout, and returns curl's failure
status for connection errors or HTTP 4xx/5xx responses. They do not create test
fixtures, depend on one another, or clean up resources. `retrieve.sh` also
validates the flat response shape when `target_media` is supplied.

Set `ENGINE_URL` to target another engine; it defaults to
`http://localhost:${ENGINE_PORT:-16022}`. `CURL_TIMEOUT` defaults to `120` seconds,
and `ASSET_LOOKUP_PAGE_SIZE` defaults to `1000000` for asset-name resolution.
These shared settings are defined once in `lib.sh`.
JSON arguments may be inline strings or curl's `@file`
form. Relative `@file` paths are resolved from this scripts directory. `jq` is
required and pretty-prints every JSON response automatically. Ready-to-edit
create payloads live in [`example/`](example/).

Every object reference accepts either its `id` or its unique `name`. Helpers
resolve names to IDs before constructing a URL or request body. An exact ID wins
over a name collision; an ambiguous name fails and asks for an ID. Database
registrations use their human-chosen `id` as their display name because they do
not have a separate `name` field.

```bash
cd data-intelligence-engine/scripts

./status.sh health
ENGINE_URL=http://engine-host:16022 ./databases.sh read
./databases.sh create @example/database.json
./library.sh read docs
```

## Deployment scripts

Two scripts here set the engine up rather than call its API:

| Script | What it does | Guide |
|---|---|---|
| `quickstart.sh` | Takes a clean host to a running engine: workspace, `.env`, image (built when missing or with `--build`), models (on the first run or with `--model`/`--models`), Milvus, engine, `local-milvus` registration; `--down` stops and removes the services and keeps the workspace | [Get Started](../docs/user-guide/get-start.md#step-1-deploy) |
| `prepare-models.sh` | Downloads and converts the models (by default GME, bge-reranker-large, PP-DocLayoutV3, ViCLIP-B, Whisper and the Qwen3-VL INT8 media reranker) in throwaway engine containers | [Prepare models with one script](../docs/user-guide/how-to-guides/how-to-prepare-models.md#prepare-models-with-one-script) |

Run either with `--help` for its options.

Video models and export instructions are listed in [Model preparation](../docs/user-guide/how-to-guides/how-to-prepare-models.md#45-viclip-short-videos).

## Helpers

### Service, databases, and models

```bash
./status.sh health
./status.sh databases
./status.sh backends
./status.sh check <database-name-or-id>
./status.sh models [embedding|reranker]
./status.sh model-names <embedding|reranker>
./status.sh devices
```

### Database CRUD

```bash
./databases.sh create @example/database.json
./databases.sh create @example/content-database.json
./databases.sh create @example/graph-database.json
./databases.sh read
./databases.sh read local-milvus
./databases.sh update local-milvus '{"description":"primary vectors"}'
./databases.sh check local-milvus
./databases.sh delete local-milvus
./databases.sh backends
```

### Asset-library CRUD

```bash
./library.sh create @example/library.json
./library.sh read
./library.sh read docs
./library.sh update docs '{"description":"Current documentation"}'
./library.sh delete docs
```

### Sources

```bash
./sources.sh create docs @example/source.json        # vector source
./sources.sh create docs @example/graph-source.json  # graph source (OKF bundles)
./sources.sh create docs @example/graph-source-with-extractor.json
./sources.sh read
./sources.sh read docs
./sources.sh update docs primary '{"enabled":false}'
./sources.sh delete docs primary
```

`update` changes only `name`, `labels` and `enabled`; a source's model and
parameters are fixed. `collection_name` may be omitted on create.

With no library argument, `read` returns a flat array containing the sources
from every asset library.

`database_id` remains the source relationship field, but source create payloads
may put a database name or ID in it; the helper normalizes it to the ID.

For a graph source, `operator_options.asset_types` selects the knowledge
formats: `["okf"]` (the default) builds the graph from OKF bundles; `["okf",
"document"]` also accepts documents and needs `external_extractor` (`url`,
optional `api_key`, `timeout`, `options`) for the service that turns documents
into OKF bundles. The service reviews all task content to generate extraction
instructions, then returns a JSON path to an OKF bundle in the shared
`ENGINE_UPLOAD_DIR`. Both containers must mount the same upload directory;
files are not transferred over HTTP or ZIP. A vector source in the same pool
must already hold the documents' chunks for provenance. The engine refuses a graph
source with an unknown format
or a missing/invalid extractor, and reports `api_key` masked. See the
[service guide](../tools/okf_extractor/README.md) for deployment and task schemas.

### Asset pools

```bash
./pools.sh create docs @example/pool.json
./pools.sh create docs @example/pool-with-graph.json   # vector + graph source
./pools.sh read
./pools.sh read docs
./pools.sh read docs DefaultPool
./pools.sh sources
./pools.sh sources docs
./pools.sh sources docs DefaultPool
./pools.sh assets
./pools.sh assets docs
./pools.sh assets docs DefaultPool
./pools.sh update docs DefaultPool '{"sources":["primary"]}'
./pools.sh add-sources docs DefaultPool graph
./pools.sh remove-sources docs DefaultPool graph
./pools.sh add-sources docs DefaultPool primary
./pools.sh add-sources docs DefaultPool primary-v2 --replaces primary
./pools.sh routing docs DefaultPool
./pools.sh add-assets docs DefaultPool '{"asset_ids":["manual.pdf"]}'
./pools.sh graph docs DefaultPool [limit]
./pools.sh delete docs DefaultPool
```

With no library argument, `read` returns a flat array containing the pools from
every asset library. `sources` and `assets` also accept no filter, one library
name/ID, or an exact library and pool pair. `update` replaces the complete
attached-source list. `add-sources` and `remove-sources` read the current list
and merge or drop the supplied source names/IDs; a pool keeps at least one
source. With `--replaces`, the one new source takes over from the named one
once it has caught up; the deprecated source stays attached for rollback.
`graph` returns the pool's OKF concept graph (`nodes`, `edges`, `total`,
`truncated`), the same data the console draws. Source references in
create/update JSON and asset references in add-assets JSON follow the same
name-or-ID rule.

`routing` is read-only. It shows which source takes each kind of content in the pool, and in which state, and lists the kinds that no serving source covers.
For example, `video-viclip-l` serves video queries while `video-viclip-b` is kept `DEGRADE` for rollback:

```json
{
  "pool_id": "DefaultPool",
  "routes": {
    "text": [
      {"source_name": "primary",        "via": "text",       "serving_state": "SERVING",    "effective_state": "SERVING"}
    ],
    "image": [
      {"source_name": "image-gme",      "via": "vector",     "serving_state": "SERVING",    "effective_state": "SERVING"}
    ],
    "short_video": [
      {"source_name": "video-viclip-b", "via": "vector",     "serving_state": "DEGRADE", "effective_state": "DEGRADE"},
      {"source_name": "video-viclip-l", "via": "vector",     "serving_state": "SERVING",    "effective_state": "SERVING"}
    ],
    "long_video": [],
    "audio": [
      {"source_name": "audio-gme",      "via": "transcript", "serving_state": "SERVING",    "effective_state": "SERVING"}
    ]
  },
  "uncovered": ["long_video", "l2_caption", "l3_wiki"]
}
```

The output is abbreviated: the real one also has `source_id`, and a route for every role (`doc_image`, `l1_segment`, `l2_caption`, `l2_transcript`, `l3_wiki`).
`via` is `vector` (the model embeds the content itself), `caption` (a text model embeds a media block's caption), `transcript` (a model embeds a recording's transcript), `text` or `graph`.
`asset_types` filters are not reflected.

### Assets

```bash
# Upload local files or folders and ingest them (flag form)
./assets.sh add docs manual.pdf ./okf_bundle/ ./reports/ --pool DefaultPool --wait
./assets.sh add docs --text "Inline note to index" --pool DefaultPool

# Same from a JSON body (AssetCreateRequest)
./assets.sh create docs @example/assets.json --wait

./assets.sh upload docs manual.pdf ./okf_bundle/    # stage only; prints file_paths
./assets.sh read docs
./assets.sh read docs 2 50
./assets.sh wait docs manual.pdf okf_bundle
./assets.sh delete docs '{"asset_ids":["manual.pdf"]}'
./assets.sh delete-one docs manual.pdf
```

Local files and folders are uploaded through the engine's API
(`PUT /v1/libraries/{library}/uploads/{path}`), so the helpers work against a
remote engine and need no shared upload mount. A folder keeps its structure:
an OKF bundle (a folder holding an `index.md`, even one level down) is
ingested as one asset, and any other folder as its supported files. Hidden
files are skipped, and the engine skips unsupported ones. A `file_paths` entry
that does not exist locally is sent unchanged, as a path on the engine host
(a bare name is looked up in the engine's upload directory).

Ingest runs in the background: the create call returns `materializing` at once.
`--wait` (or `wait`) polls until each asset reports `ready`; `WAIT_TIMEOUT`
(seconds, default `1800`) and `WAIT_INTERVAL` (default `3`) tune it. Set
`asset_pool_ids`/`--pool` to pool names or IDs to index the assets, or leave
it empty to store them only.

Deleting removes an asset's stored content and everything indexed from it:
its chunks in vector sources and, for an OKF bundle, its concepts in graph
sources and their vectors (unless another bundle defines them too). Remaining
concepts stop citing a deleted document's chunks. The engine
refuses, changing nothing, if a source is unavailable or a deleted bundle's
files can no longer be read.

### Retrieval

For explicit video/image/audio retrieval, use `retrieve.sh` to call the
same endpoint and validate its flat `retrieved_chunks` / `chunks` response:

```bash
./retrieve.sh query multimedia-poc 'a person is talking' --target-media video,image --top-k 3
```

The media targets are searched independently; audio requires a serving
transcript projection. See [text-to-media-retrieval.md](../docs/user-guide/text-to-media-retrieval.md)
for request fields, response semantics, and test steps.

For media reranking, add `--rerank` or send JSON with `postprocess`:

```bash
./retrieve.sh query multimedia-poc 'red bag' --target-media image,video --top-k 20 --rerank 3
```

`top_k` sets candidate depth per serving source; `top_n` limits the final global
result count after reranking. The model export, parity, machine review, annotation,
and frozen evaluation commands live in
[text-to-media-retrieval.md](../docs/user-guide/text-to-media-retrieval.md#prepare-the-openvino-model)
and use the Python tools in this directory.

```bash
# Flag form
./retrieve.sh query docs "thermal limits"                          # rrf, every pool
./retrieve.sh query docs "thermal limits" --pool DefaultPool --type graph --top-k 5
./retrieve.sh query docs "thermal limits" --type bm25 --rerank 3
./retrieve.sh query docs "thermal limits" --rerank 3 --reranker BAAI/bge-reranker-large --trace

# JSON form
./retrieve.sh @example/retrieve.json
./retrieve.sh '{
     "query":"thermal limits",
     "libraries":["docs"],
     "asset_pool_ids":["DefaultPool"],
     "top_k":5,
     "retriever_type":"rrf",
     "include_graph_trace":true,
     "postprocess":{"processor_type":"reranker","top_n":3}
}'
```

`--type` / `retriever_type` is one of `rrf` (default; vector + BM25 + graph,
fused by reciprocal rank, falling back to vector similarity on a pool without a
graph source), `vectorsimilarity`, `bm25` or `graph`. Without `--pool` every
pool in the library is searched. `--rerank N` reranks to the top N with the
engine's default reranker, or `--reranker MODEL`. `--trace` adds
`graph_traces` for `rrf`/`graph` (seeds, concepts reached by hop, links
walked, and which concepts contributed result chunks); `--type graph` always
includes it.

The helper resolves each library and pool reference. With several libraries, a
pool name must resolve to the same pool ID in every library; use explicit
shared IDs otherwise.

Multiple vector sources are queried independently, each contributes up to
`top_k` candidates, and the source result lists are interleaved round-robin
rather than fused or globally sorted across embedding models.
ViCLIP and GME scores are not calibrated to each other. To avoid one model's
scores dominating, place those sources in separate pools and issue separate
queries with `--pool` / `asset_pool_ids`; that field selects pools, not sources.
Text vector/BM25/graph RRF within a pool retains the behavior described above.

Run any helper with `--help` for its accepted operations and arguments.

## Skills for agent

For an external agent, [`../skills/knowledgebase`](../skills/README.md) packages
the same `POST /v1/retrieve` request as a self-contained skill: its
`data_intelligence_engine` wrapper needs only `bash` and `curl`, takes its
defaults from `KB_*` environment variables, and prints the chunks as a numbered
list for the agent to answer from.

```bash
KB_LIBRARY=docs ../skills/knowledgebase/data_intelligence_engine "thermal limits" --media document --rerank 3
```
