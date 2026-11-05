# How to ingest multimodal data

To ingest more kinds of files than the text file in [Get Started](../get-start.md)
(PDFs, images, videos, audio or OKF knowledge bundles), follow this guide. It
continues from that deployment: the engine runs on `http://localhost:16022` with
Milvus registered as `local-milvus`. Every content type follows the same steps:
prepare its models, create a source and a pool, ingest, then retrieve.

Run the commands from `data-intelligence-engine/scripts`. The scripts bypass any
proxy for `localhost` themselves; for the `curl` calls below behind a proxy, run
`export no_proxy=localhost,127.0.0.1,$no_proxy` first.

## Contents

- [1. Prepare models](#1-prepare-models)
- [2. Create a library](#2-create-a-library)
- [3. Source options](#3-source-options)
- [4. Ingest files](#4-ingest-files)
  - [Videos](#videos)
  - [Images](#images)
  - [Audio](#audio)
  - [PDFs](#pdfs)
  - [OKF knowledge graphs](#okf-knowledge-graphs)
- [5. Check status](#5-check-status)
- [6. Retrieve](#6-retrieve)
- [7. Media reranking](#7-media-reranking)
- [Notes](#notes)
- [Appendix: inspect data with web UIs (for dev)](#appendix-inspect-data-with-web-uis-for-dev)
  - [Milvus (Attu)](#milvus-attu)
  - [NebulaGraph (Studio)](#nebulagraph-studio)
  - [MinIO](#minio)
- [Appendix: replace a source](#appendix-replace-a-source)
- [Appendix: delete ingested data](#appendix-delete-ingested-data)
  - [Remove some assets](#remove-some-assets)
  - [Remove everything for one library](#remove-everything-for-one-library)
  - [Reset the whole dev environment](#reset-the-whole-dev-environment)
- [Appendix: the engine workspace (for dev)](#appendix-the-engine-workspace-for-dev)

## 1. Prepare models

The engine never downloads or converts models at runtime. On its first run
`quickstart.sh` prepares every model this guide uses: GME, bge-reranker-large,
PP-DocLayoutV3, ViCLIP-B, Whisper and the Qwen3-VL INT8 media reranker. If your
models were prepared before that, or you want an alternative such as ViCLIP-L,
add them with `prepare-models.sh`, which skips models already in place:

```bash
./prepare-models.sh                    # the default set
./prepare-models.sh viclip-l           # an alternative video model
```

See [How to prepare models](how-to-prepare-models.md) for every model. Paths
below are relative to `data-intelligence-engine/workspace/models/`. Select a
prepared package with `operator_options.embedding_model`: a local model ID names
its directory under that root, and each weight variant has its own model ID.

| Data | Model / indexed content | Prepared directory |
|---|---|---|
| Video | ViCLIP-B (`viclip-b-fp16`, default), ViCLIP-L or Cosmos-224p, original video | `viclip-b-fp16/`, `viclip-l-fp16/` or `cosmos-224p-fp16/`; each also supports an `fp32` package |
| Images / video captions | GME-Qwen2-VL-2B, pixels / derived caption text | `gme-Qwen2-VL-2B-Instruct-OV/` |
| Audio | Whisper-small → GME, transcript text | `whisper-small/openvino/` + GME above |
| PDFs / OKF document corpus | Native GME, document text and PDF figures | GME above; PDFs also need `PP-DocLayoutV3/pp_doclayout_v3.onnx` |

Scanned PDFs are read with Tesseract, which the engine image includes with
Chinese and English data.

## 2. Create a library

```bash
./library.sh create '{"name":"my-library"}'
```

A library holds assets, a source says where vectors go, and a pool binds assets
to sources. If you run the engine from a local Python environment instead of
`quickstart.sh`, first register Milvus as `local-milvus` with the URI
`http://localhost:19530` (see the [database API](../api.md#databases)).

## 3. Source options

`operator_options` belongs to source creation, not the ingest request.

| Field | Required? | Purpose / default |
|---|---|---|
| `asset_types` | **Yes for standalone media** | Nonempty array: `["video"]`, `["image"]` or `["audio"]`. Extensions/MIME types such as `["mp4"]` narrow file scope. Optional for documents (`["pdf"]` restricts files); graph sources default to `["okf"]`. |
| `block_roles` | No | Select representation. Omitted: video → original video, image → pixels, audio → `l2_transcript`. `["l2_caption"]` on video selects GME caption text. `[]` adds no role filter. |
| `block_kinds` | No | Advanced block filter, **not** a model selector. Omitted: derived from representation; `[]` adds no kind filter. Must be compatible with the representation/model. |
| `embedding_model` | No | Select a prepared model by ID under `ENGINE_MODEL_ROOT_PATH`. Omitted: category default. Use a separate model ID for each weight variant. Must support the selected representation. |
| `embedding_backend` / `embedding_device` | No | Override runtime / device; otherwise use the model category's engine defaults. |
| `max_image_tokens` | No | GME visual-token limit; defaults to the package setting. |
| `frames_per_clip` | No | Fixed at `8` for all video models; must match the package. |
| `chunk_size` / `chunk_overlap` / `figure_context_chars` | No | Document chunking and PDF figure context; engine defaults apply. |

- One source = one frozen model/vector space. Use separate sources and collections
  for video pixels and captions. Filters select content; they do not generate it.
- Document/PDF and existing OKF ingestion need no `operator_options` with default
  settings.

## 4. Ingest files

Run only the sections needed. Each follows **source → pool → ingest**.
`assets.sh add` uploads files or folders through the engine API; a normal folder
ingests its supported files. Re-ingesting a file replaces its vectors, so a
repeated run creates no duplicates. `--wait` waits for asset materialization,
**not** captioning/transcription or completion of every source sync; see
[Check status](#5-check-status).

### Videos

ViCLIP-B embeds known videos ≤ 60 seconds and existing `l1_segment` blocks,
sampling eight frames for one vector; its own text encoder embeds queries. Long
or unknown-duration videos are stored but uncovered; the engine does not split
them.

```bash
./sources.sh create my-library '{
  "name":"video-viclip-b",
  "database_id":"local-milvus",
  "collection_name":"my_library_video_viclip_b",
  "operator_options":{"asset_types":["video"],"embedding_model":"viclip-b-fp16"}
}'
./pools.sh create my-library '{
  "id":"video-segments","name":"Videos","sources":["video-viclip-b"]
}'
./assets.sh add my-library ../data/videos/my_video_segments \
  --pool video-segments --wait
```

For Cosmos, use `"embedding_model":"cosmos-224p-fp16"` and a separate collection.

Optional: index captions of the **same assets** in parallel, without re-uploading
or replacing the video encoder. Set `ENGINE_VIDEO_SUMMARY_BASE_URL` to an
already-running caption service in `deployment/docker/.env` before starting the
engine; this integration is not yet verified end to end.

```bash
./sources.sh create my-library '{
  "name":"video-caption-gme",
  "database_id":"local-milvus",
  "collection_name":"my_library_video_caption_gme",
  "operator_options":{"asset_types":["video"],"block_roles":["l2_caption"],"embedding_model":"gme-Qwen2-VL-2B-Instruct-OV"}
}'
./pools.sh add-sources my-library video-segments video-caption-gme
```

Caption updates resync caption consumers, not ViCLIP video vectors.

### Images

GME puts text and images in one space, so a text query finds pictures. Attaching
the source loads the model (about 5 s on CPU with int8 weights); each image then
takes about 1-2 s on CPU. `max_image_tokens` is the main latency knob.

```bash
./sources.sh create my-library '{
  "name":"image-gme-embeddings",
  "database_id":"local-milvus",
  "collection_name":"my_library_image_gme",
  "operator_options":{"asset_types":["image"],"embedding_model":"gme-Qwen2-VL-2B-Instruct-OV"}
}'
./pools.sh create my-library '{
  "id":"images","name":"Images","sources":["image-gme-embeddings"]
}'
./assets.sh add my-library ../data/images --pool images --wait
```

### Audio

After ingest, Whisper transcribes each recording in the background and GME embeds
the transcript, not the raw audio. Mandarin is the default; for another language,
set `ENGINE_ASR_LANGUAGE` (for example `en`) in `deployment/docker/.env` and run
`quickstart.sh` again to recreate the engine container.

```bash
./sources.sh create my-library '{
  "name":"audio-gme",
  "database_id":"local-milvus",
  "collection_name":"my_library_audio_gme",
  "operator_options":{"asset_types":["audio"],"embedding_model":"gme-Qwen2-VL-2B-Instruct-OV"}
}'
./pools.sh create my-library '{"id":"audio","name":"Audio","sources":["audio-gme"]}'
./assets.sh add my-library ../data/audio/my_recordings --pool audio --wait
```

A recording is searchable once its `/enrichment` reports `transcript_status:
completed` and `embedding_status: ready` (see [Check status](#5-check-status)).
Each 30-second stretch of speech is one result, with `t_start_ms` and `t_end_ms`.

### PDFs

Default native GME handles text chunks and extracted figures, which it embeds
with their reference text; PP-DocLayoutV3 detects the figures, and scanned PDFs
cannot be read without it. `asset_types` below only restricts file scope; omit
`operator_options` for general document ingestion.

```bash
./sources.sh create my-library '{
  "name":"pdf-gme",
  "database_id":"local-milvus",
  "collection_name":"my_library_pdf_gme",
  "operator_options":{"asset_types":["pdf"],"embedding_model":"gme-Qwen2-VL-2B-Instruct-OV"}
}'
./pools.sh create my-library '{
  "id":"pdf-documents","name":"PDFs","sources":["pdf-gme"]
}'
./assets.sh add my-library ../data/mmdir/my_pdfs --pool pdf-documents --wait
```

A digital PDF's text becomes searchable before its figures are done; the asset's
`materialization` moves from `text_ready` to `ready`. Keep this document source
separate from standalone-image sources to avoid indexing the same extracted
illustration twice.

### OKF knowledge graphs

Ingest an existing OKF concept bundle together with its original documents. This
does not extract OKF from documents.

```text
data/okf/my_dataset/
├── corpus/          # original documents; preserve paths referenced by source_files
│   ├── doctors/
│   ├── records/
│   └── residents/
└── okf_bundle/      # one OKF asset: index.md + concept subdirectories
    ├── index.md
    ├── doctor/
    └── resident/
```

Milvus holds document/concept vectors and NebulaGraph holds concepts and links.
Keep both sources, the complete corpus and the bundle in the **same pool**. Start
NebulaGraph and register it; the engine container reaches it by its service name
on the shared network:

```bash
docker compose -f ../deployment/docker/docker-compose-nebula.yml up -d
curl -X POST http://localhost:16022/v1/databases -H 'Content-Type: application/json' -d '{
  "id":"local-nebula","type":"graph","backend":"nebula",
  "options":{"url":"nebula://nebula-graphd:9669"}}'
curl -X POST http://localhost:16022/v1/databases/local-nebula/check
```

Continue once the check returns `reachable: true`. `username` defaults to `root`,
and `password` can be omitted while Nebula's authorization is disabled, which is
this stack's default; otherwise add both to `options`. Use the client port
`9669`; `19669` is only for HTTP status checks.

```bash
./library.sh create '{"name":"knowledge-library"}'
./sources.sh create knowledge-library '{
  "name":"knowledge-text","database_id":"local-milvus",
  "collection_name":"my_knowledge_text_gme"
}'
./sources.sh create knowledge-library '{
  "name":"knowledge-graph","database_id":"local-nebula",
  "collection_name":"my_knowledge_concepts",
  "operator_options":{"asset_types":["okf"]}
}'
./pools.sh create knowledge-library '{
  "id":"knowledge-documents","name":"Knowledge",
  "sources":["knowledge-text","knowledge-graph"]
}'
./assets.sh add knowledge-library \
  ../data/okf/my_dataset/corpus ../data/okf/my_dataset/okf_bundle \
  --pool knowledge-documents --wait
```

Upload `corpus` and `okf_bundle` as directories, as shown: one asset per
supported document, plus one bundle asset recognized by its `index.md`. Do not
flatten the corpus or upload only `index.md`. After both sources finish syncing,
inspect the graph:

```bash
./pools.sh read knowledge-library knowledge-documents \
  | jq '.source_statuses[] | {source_id, status, serving_state, error}'
./pools.sh graph knowledge-library knowledge-documents 20
```

## 5. Check status

Ingest returns `202` / `materializing`. An empty pool can already report ready;
check the assets and source sync, then media enrichment if needed.

```bash
./assets.sh read my-library 1 1000 \
  | jq '.assets[] | {id, name, materialization}'
./pools.sh read my-library video-segments \
  | jq '.source_statuses[] | {source_id, status, serving_state, error}'
./pools.sh routing my-library video-segments

ASSET_ID="<asset-id-from-list>"
curl -sS "http://localhost:16022/v1/libraries/my-library/assets/$ASSET_ID/enrichment" \
  | jq '{caption_status, transcript_status, embedding_status, embedding_reason}'
```

| Check | Ready / action |
|---|---|
| Asset `materialization` | `ready` |
| Required source sync | `status: ready`, `serving_state: SERVING`, no error; on `failed`, inspect `error` |
| Media `embedding_status` | `ready`; on `no_source` / `failed`, inspect `embedding_reason` |
| Caption / transcript | Check separately when required; caption `skipped` is expected without a caption service |

## 6. Retrieve

```bash
./retrieve.sh query my-library "a person sitting up in bed" \
  --pool video-segments --type vectorsimilarity --top-k 3
./retrieve.sh query my-library "a nurse bringing water" \
  --pool images --type vectorsimilarity --top-k 3
./retrieve.sh query my-library "What does the architecture diagram show?" \
  --pool pdf-documents --type vectorsimilarity --top-k 5
./retrieve.sh query knowledge-library "Which doctor is responsible for resident 001?" \
  --pool knowledge-documents --type rrf --top-k 10 --trace
```

Repeat `--pool` to search several pools, or omit it to search the whole library.
For OKF, `--type graph` shows only the graph arm and its trace back to document
chunks. The same call from Python, as a retriever would make it:

```python
import httpx

response = httpx.post(
    "http://localhost:16022/v1/retrieve",
    json={"query": "a person sitting up in bed", "libraries": ["my-library"], "top_k": 3},
    timeout=60,
)
response.raise_for_status()
for chunk in response.json()["chunks"]:
    print(f'{chunk["score"]:.3f}  {chunk["metadata"]["file_name"]}')
```

- **Results:** videos, images, transcript chunks, PDF text/illustrations, or
  document chunks cited by OKF concepts. `source_id` identifies the source and
  `pool_id` the pool.
- **Scores:** vector sources are searched independently, taking up to `top_k`
  candidates per source, and the lists are interleaved round-robin. Scores are
  not calibrated across models, so use separate pools to inspect model rankings
  independently, or rerank (below).
- **OKF:** results are document chunks with graph traces, not generated answers.
  Missing document chunks usually mean the full corpus is absent, its paths
  changed, or text sync has not finished. Graph retrieval uses only the first
  serving text source; replacing it does not yet migrate graph provenance or the
  concept index.

## 7. Media reranking

Add `"postprocess":{"processor_type":"reranker","top_n":3}` to a media request;
the Qwen3-VL INT8 media reranker is among the default models.
`top_k` controls candidates per source; `top_n` limits the final global ranking.
Without a usable GPU, set `ENGINE_MEDIA_RERANK_DEVICE=CPU` in
`deployment/docker/.env` and run `quickstart.sh` again. See
[Media reranking](../text-to-media-retrieval.md#media-reranking) for examples,
model options and failure behavior.

## Notes

- **Video limit:** video embedding does not cover segments over 60 seconds. Check
  `/enrichment` for missing coverage.
- **GME memory:** document and image sources share a runtime only with the same
  model package and device. Compose defaults to document GPU / image CPU; align
  devices to avoid loading two copies.
- **Model errors:** if attaching a source returns `503`, check the error for
  missing model files or incorrect paths; see
  [When attaching a source fails](../user-guide.md#when-attaching-a-source-fails).
- **Changing a model:** a source's model is fixed at creation; to switch, replace
  the source as in [Appendix: replace a source](#appendix-replace-a-source).

## Appendix: inspect data with web UIs (for dev)

### Milvus (Attu)

Milvus has no built-in UI. Attu is its web console, and its version must match Milvus. This stack runs Milvus v2.4.x, so use Attu v2.4.x. The `latest` tag only connects to Milvus 2.6 and later.

```bash
docker run -d --name attu --restart unless-stopped \
  --network data-intelligence-network -p 33000:3000 zilliz/attu:v2.4.12
```

Open `http://<host>:33000` and connect with address `milvus-standalone:19530` and authentication **None**.
Use the container-network service name, not `localhost`.
Your collection (`my_library_video_viclip_b`) holds one 512-dimension record per video segment, with the fields above.

### NebulaGraph (Studio)

- **Start:** Studio is a separate web console. Studio v3.8.0 supports this stack's
  NebulaGraph v3.6.0. [Start NebulaGraph](#okf-knowledge-graphs) first,
  then run Studio on the same Docker network:

```bash
docker run -d --name nebula-studio --restart unless-stopped \
  --network data-intelligence-network -p 7001:7001 \
  vesoft/nebula-graph-studio:v3.8.0
```

- **Connect:** Open `http://<host>:7001`; enter `nebula-graphd:9669`, username
  `root` and any password (authorization is disabled). Do not use `localhost` or a `nebula://` prefix.
  Port `19669` is for status checks, not Studio. Authorization is disabled by
  default; keep this dev stack off public networks.
- **Wait for the data, not the webpage:** Studio can open before ingestion
  finishes. `reachable: true` only confirms database connectivity. For this
  initial OKF ingest, wait for:
  - All returned assets to be registered with `materialization: ready`.
  - Both `knowledge-text` and `knowledge-graph` to report `status: ready`,
    `serving_state: SERVING` and `error: null`.
  - The pool graph query to return nodes and edges for a bundle containing links.
    An empty pool can also report `ready`, so check the assets and graph too.

```bash
# Run from data-intelligence-engine/scripts; repeat the reads while ingestion is in progress.
./assets.sh read knowledge-library 1 1000 \
  | jq '.assets[] | {name, materialization}'
./pools.sh read knowledge-library knowledge-documents \
  | jq '.source_statuses[] | {source_id, status, serving_state, error}'
# After the checks above pass, verify graph contents.
./pools.sh graph knowledge-library knowledge-documents 20
```

- **First-build time:** Corpus chunking/embedding runs before OKF graph writes
  and concept embedding; Nebula also waits for space/schema propagation. There
  is no measured end-to-end ETA. For hundreds of documents on CPU, budget tens
  of minutes or longer, depending on chunk count and hardware. `knowledge-text:
  indexing` with `knowledge-graph: pending` means the graph stage is waiting for
  text sync. A `failed` status requires checking `error`, not more waiting.
- **Inspect:** Select space `my_knowledge_concepts` (the graph source's
  `collection_name`). **Schema** shows tag/edge definitions, not automatically
  a populated data graph. Run these queries in **Console** to inspect records:

```ngql
SHOW SPACES;
USE my_knowledge_concepts;
SHOW TAGS;
SHOW EDGES;
MATCH (v) RETURN v LIMIT 10;
MATCH p=(a)-[e]->(b) RETURN p LIMIT 10;
```

- **Empty vs blank:** An empty space/result can mean ingestion is unfinished or
  the wrong space is selected. A completely blank browser page is a UI-loading
  issue, not a graph-readiness signal; check Studio's logs and browser errors.

```bash
docker logs --tail 50 nebula-studio
curl -I http://localhost:7001/
```

- **Storage:** Nebula holds concepts and links; document chunks and concept
  vectors stay in Milvus. [Official Studio deployment guide](https://docs.nebula-graph.io/3.6.0/nebula-studio/deploy-connect/st-ug-deploy/#docker-based_studio).

### MinIO

The console is at `http://<host>:9001`. Sign in with `minioadmin` / `minioadmin`, the compose defaults. Change them for any shared deployment.
Ports come from `MINIO_API_PORT` and `MINIO_CONSOLE_PORT` in `data-intelligence-engine/deployment/docker/.env`.

This MinIO is Milvus's internal storage. `a-bucket` holds Milvus segment files and index data, not your videos.
By default the engine keeps content records on the filesystem under `data-intelligence-engine/workspace/content/`, and the videos stay in `data-intelligence-engine/workspace/uploads/<library-id>/`:

```bash
ls data-intelligence-engine/workspace/content/*/assets    # one JSON content record per asset
ls data-intelligence-engine/workspace/uploads/*/          # the video files themselves
```

## Appendix: replace a source

A source's model and parameters are fixed at creation. Another checkpoint or
weight variant means a new source naming a different prepared model ID, replacing
the old one in its pool. No re-ingest is needed; old vectors stay until deleted.

Example: switch from `viclip-b-fp16` (512 dimensions) to the separately prepared
`viclip-l-fp16` package (768 dimensions); see
[Video model preparation](how-to-prepare-models.md#45-viclip-short-videos).
Use a **new collection** for the new vector space.

Check which source covers each kind of content before the switch:
```bash
./pools.sh routing my-library video-segments
```

```bash
# 1. New source and collection. embedding_model selects the prepared package.
./sources.sh create my-library '{
  "name":"video-viclip-l",
  "database_id":"local-milvus",
  "collection_name":"my_library_video_viclip_l",
  "operator_options":{"asset_types":["video"],"embedding_model":"viclip-l-fp16"}
}'

# 2. Attach it, replacing video-viclip-b
./pools.sh add-sources my-library video-segments video-viclip-l --replaces video-viclip-b

# 3. Watch the switch
./pools.sh read my-library video-segments \
  | jq '.source_statuses[] | {source_id, status, serving_state}'
```

Check the routing again afterwards -- the new source should now answer for `short_video`:
```bash
./pools.sh routing my-library video-segments
```

- While the new source is `PREPARING`, the pool keeps answering from the old one.
- Once it has re-embedded every asset, it becomes `SERVING` and the old one becomes `DEGRADE` -- its vectors stay in Milvus, its model is unloaded.
- Rollback is the same command in the other direction: `--replaces video-viclip-l` with `video-viclip-b` attached again.

The console shows `serving_state` per pool in the Sources list and canvas
inspector. Choose `DEGRADE` to stop that binding, or `SERVING` to resume it;
its stored vectors are kept. A resumed source behind the pool reports `PREPARING`
until ready. This does not replace or stop another source; use `--replaces` above
for coordinated replacement. Removing a canvas link instead detaches the binding.

Even weight variants of the same checkpoint can produce different scores; the
new source rebuilds vectors before taking over. The same procedure applies to a
different checkpoint. Every supported video package fixes `frames_per_clip`
at eight; a mismatch is refused at attach.

The same works for images: prepare a separate
`gme-Qwen2-VL-2B-Instruct-OV-int4` package, create a source with
`"embedding_model":"gme-Qwen2-VL-2B-Instruct-OV-int4"`, then replace
`image-gme-embeddings`.

Where every model goes, and how to convert or check it: [How to prepare embedding models](how-to-prepare-models.md).

## Appendix: delete ingested data

Each level removes less than you might expect. Deleting a pool, a source or a library only removes the engine's configuration.
It never touches the vectors in Milvus or the stored files. Only deleting assets removes vectors, and Milvus has no engine API to drop a collection.

| To remove | Run | Vectors in Milvus | Media files |
|---|---|---|---|
| Some assets | `assets.sh delete-one` / `delete` | removed | content record removed, and the file too if it is in `workspace/uploads/` |
| A pool | `pools.sh delete` | **kept** | kept |
| A source | `sources.sh delete` | **kept** (collection stays) | kept |
| A library | `library.sh delete` | **kept** | **kept** |
| A Milvus collection | `pymilvus` or Attu | removed | kept |

Run these from `data-intelligence-engine/scripts`.

### Remove some assets

```bash
./assets.sh delete-one my-library <asset-name-or-id>
```

For several, put `{"asset_ids": ["<id>", "<id>"]}` in a file and run `./assets.sh delete my-library @file.json`.
Find ids with `./pools.sh assets my-library video-segments`.
Re-ingesting a deleted file works as a fresh ingest, but deleting the asset removed the file from `uploads/`, so stage it again with `assets.sh create`.
A file you ingested from an absolute path outside `uploads/` is left in place.

### Remove everything for one library

**Order matters**. Delete the assets first: that clears the vectors, and a library's content store cannot be detached while assets still use it.
Look up the content store before deleting the library, because the library is gone afterwards.

```bash
LIB=my-library; POOL=video-segments

# 1. Assets: removes their vectors and content records
./pools.sh assets $LIB $POOL | jq '{asset_ids: .}' > /tmp/assets.json
./assets.sh delete $LIB @/tmp/assets.json

# 2. Note this library's content store id (it holds the content records)
CONTENT_ID=$(./sources.sh read $LIB | jq -r '.[] | select(.type=="object") | .collection_name')

# 3. Configuration: pool, source, library
./pools.sh delete $LIB $POOL
./sources.sh delete $LIB video-viclip-b
./library.sh delete $LIB

# 4. The now-empty Milvus collection, dropped with the pymilvus in the engine image
docker exec data-intelligence-engine python -c 'from pymilvus import MilvusClient
MilvusClient(uri="http://milvus-standalone:19530").drop_collection("my_library_video_viclip_b")'

# 5. The library's content directory (the records are already gone; this clears leftovers)
docker exec data-intelligence-engine rm -rf "/workspace/content/${CONTENT_ID:?}"
```

Skip step 4 or 5 to keep the empty collection or the content directory. The media files were already removed with their assets in step 1 if they were in `uploads/`.
Dropping a collection from Attu's Collections page does the same as step 4.

### Reset the whole dev environment

This removes every library, every vector and all uploads. It keeps the prepared models.

```bash
cd data-intelligence-engine
scripts/quickstart.sh --down
sudo sh -c 'rm -rf workspace/milvus/*/* workspace/content/* workspace/uploads/* workspace/configs/*.json'
```

The shell is started by `sudo` so the globs expand as root: Milvus's `etcd` and `minio` folders are not readable by your user, and the engine container writes as UID 1000.
Only the contents are removed, so the folders stay, and you do not need to repeat the `mkdir` from [Start the services](../get-start.md#step-1-deploy).
Start the services again with `scripts/quickstart.sh`, which also registers Milvus again.

## Appendix: the engine workspace (for dev)

Everything the engine keeps lives under `data-intelligence-engine/workspace/`, mounted into the engine container as `/workspace`. Know who writes each directory before you clean one up.

| Directory | What is in it | Written by | Read by |
|---|---|---|---|
| `configs/` | `asset_library.json` (libraries, sources, pools, assets) and `databases.json` (connections) | the engine, on every change | the engine at startup |
| `content/<library-id>/assets/` | one JSON content record per asset: its metadata, caption and a pointer to the media | the engine at ingest, and again when a caption arrives | the engine when it indexes, captions and retrieves |
| `content/<library-id>/blobs/` | bytes with no file of their own, named by SHA-256. Today that is only the figures extracted from a PDF | the engine at ingest | the engine when it embeds a figure |
| `uploads/<library-id>/` | the files you ingest. **For a video, image or audio file this is the asset itself**, not a staging copy | the engine, when `assets.sh` or another client uploads a file through the API | the engine: ingest, embedding and captioning open the file here directly |
| `milvus/{etcd,minio,db}` | Milvus metadata, segment files and local data | the Milvus containers (compose bind mounts) | Milvus only |
| `models/` | embedding, reranker, layout, ViCLIP, Whisper and GME model packages | you, following [How to prepare models](how-to-prepare-models.md) | the engine when it loads a model |

A video, image or audio file is not copied into the content store. Its block points at the file with a `file://` path, and the engine opens that path
for embedding and captioning. So a file in `uploads/` (or at the absolute path you gave) must stay where it is as long as its asset exists.
If you move or delete it, re-indexing and captioning fail with `origin file is gone`.

Deleting an asset deletes its file when the file is inside `uploads/`. A file you pointed at elsewhere is never deleted by the engine; the response lists it under `files_kept`.
