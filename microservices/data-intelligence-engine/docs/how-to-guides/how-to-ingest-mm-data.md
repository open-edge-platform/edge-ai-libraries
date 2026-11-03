# How to ingest multimodal data (dev)

Start the engine and databases, create a source and pool, then ingest local files
with the CLI scripts. Requires Python 3.11+, Docker Compose, `curl` and `jq`.

## 1. Prepare models

Prepare only the models needed for your data. The engine never downloads or
converts models; see [Model preparation](how-to-prepare-models.md).
Paths below are relative to `data-intelligence-engine/workspace/models/`; set
`ENGINE_MODEL_ROOT_PATH` before startup to use another model root.
Select a prepared package with `operator_options.embedding_model`: a local model
ID names its directory under that root. Each weight variant uses its own
model ID and complete package directory.

| Data | Model / indexed content | Prepared directory |
|---|---|---|
| Video | X-CLIP (`microsoft/xclip-base-patch16-zero-shot`), original video | `xclip-base-patch16-zero-shot/`, including OpenVINO video/text towers |
| Images / video captions | GME-Qwen2-VL-2B, pixels / derived caption text | `gme-Qwen2-VL-2B-Instruct-OV/` |
| Audio | Whisper-small → GME, transcript text | `whisper-small/openvino/` + GME above |
| PDFs / OKF document corpus | Native GME, document text and PDF figures | GME above; PDFs also need `PP-DocLayoutV3/pp_doclayout_v3.onnx` |

Scanned PDFs also require Tesseract and the appropriate OCR language data.

## 2. Start the services

### Local credentials

Keep service credentials in the repository-root `.env` (ignored by Git).
Replace every placeholder with your local service's configured value:

```dotenv
NEBULA_USERNAME="<nebula-username>"
NEBULA_PASSWORD="<nebula-password>"
MINIO_ROOT_USER="<minio-username>"
MINIO_ROOT_PASSWORD="<minio-password>"
```

Load this file before starting Compose or registering databases, as shown below.
Use the same values when signing in to the web consoles. Do not commit actual
credentials; keep the local file readable only by its owner (`chmod 600 .env`).
Setting these variables does not change an existing NebulaGraph account's password.

### Milvus

From the repository root:

```bash
set -a
source ./.env
set +a
cd data-intelligence-engine
mkdir -p workspace/milvus/{etcd,minio,db}

cd deployment/docker
docker network inspect data-intelligence-network >/dev/null 2>&1 \
  || docker network create data-intelligence-network
docker compose -f docker-compose-milvus.yml up -d
docker compose -f docker-compose-milvus.yml ps
```

### Engine

In another terminal, from the repository root:

```bash
cd data-intelligence-engine
source /path/to/venv/bin/activate
pip install -e . --extra-index-url https://download.pytorch.org/whl/cpu

# Optional: enable video captions with an already-running caption service.
# export ENGINE_VIDEO_SUMMARY_BASE_URL=http://caption-service:8000
# Optional: change the default ASR language (Mandarin).
# export ENGINE_ASR_LANGUAGE=en

data-intelligence-engine    # http://localhost:16022
```

### Register Milvus and create a library

In a CLI terminal, from the repository root:

```bash
set -a
source ./.env
set +a
cd data-intelligence-engine/scripts
export ENGINE_URL=http://localhost:16022

curl -sS -X POST "$ENGINE_URL/v1/databases" \
  -H 'Content-Type: application/json' -d '{
    "id":"local-milvus","type":"vector","backend":"milvus",
    "options":{"uri":"http://localhost:19530"}
  }'
curl -sS -X POST "$ENGINE_URL/v1/databases/local-milvus/check"

./library.sh create '{"name":"my-library"}'
```

Wait for the database check to return `reachable: true`. Registration is needed
only once. All remaining commands run from `data-intelligence-engine/scripts`; replace data paths
with your own. Scripts upload local files/folders, including to a remote engine.

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
| `frames_per_clip` | No | X-CLIP frame count; must match the checkpoint. |
| `chunk_size` / `chunk_overlap` / `figure_context_chars` | No | Document chunking and PDF figure context; engine defaults apply. |

- One source = one frozen model/vector space. Use separate sources and collections
  for video pixels and captions. Filters select content; they do not generate it.
- Document/PDF and existing OKF ingestion need no `operator_options` with default
  settings.

## 4. Ingest files

Run only the sections needed. Each follows **source → pool → ingest**.
`assets.sh add` accepts files or folders; a normal folder ingests its supported
files. `--wait` waits for asset materialization, **not** captioning/transcription
or completion of every source sync; check [Status](#5-check-status).

### Videos

X-CLIP embeds known videos ≤ 60 seconds and existing `l1_segment` blocks. Long or
unknown-duration videos are stored but uncovered; the engine does not split them.

```bash
./sources.sh create my-library '{
  "name":"video-xclip-embedding",
  "database_id":"local-milvus",
  "collection_name":"my_library_video_xclip",
  "operator_options":{"asset_types":["video"],"embedding_model":"microsoft/xclip-base-patch16-zero-shot"}
}'
./pools.sh create my-library '{
  "id":"video-segments","name":"Videos","sources":["video-xclip-embedding"]
}'
./assets.sh add my-library ../data/videos/my_video_segments \
  --pool video-segments --wait
```

Optional: index captions of the **same assets** in parallel, without re-uploading
or replacing X-CLIP. Configure the caption-service URL before engine startup;
this service integration is not yet verified end to end.

```bash
./sources.sh create my-library '{
  "name":"video-caption-gme",
  "database_id":"local-milvus",
  "collection_name":"my_library_video_caption_gme",
  "operator_options":{"asset_types":["video"],"block_roles":["l2_caption"],"embedding_model":"gme-Qwen2-VL-2B-Instruct-OV"}
}'
./pools.sh add-sources my-library video-segments video-caption-gme
```

Caption updates resync caption consumers, not X-CLIP vectors.

### Images

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

Background Whisper transcription is enabled by default; GME embeds its text,
not raw audio. Mandarin is the default ASR language.

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

### PDFs

Default native GME handles text chunks and extracted figures. `asset_types` below
only restricts file scope; omit `operator_options` for general document ingestion.

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

### OKF knowledge graphs

Requires Milvus **and** NebulaGraph. Ingest the complete original corpus and its
OKF bundle into the **same pool**. Preserve corpus paths referenced by the bundle's
`source_files`; upload the bundle directory (containing `index.md`), not just its
index file. This ingests an existing bundle; it does not extract OKF from documents.

```bash
# From data-intelligence-engine/scripts; the shared Docker network was created above.
docker compose -f ../deployment/docker/docker-compose-nebula.yml up -d
jq -n '{
    "id":"local-nebula","type":"graph","backend":"nebula",
    "options":{"url":"nebula://localhost:9669",
      "username":env.NEBULA_USERNAME,"password":env.NEBULA_PASSWORD}
  }' | curl -sS -X POST "$ENGINE_URL/v1/databases" \
    -H 'Content-Type: application/json' --data-binary @-
curl -sS -X POST "$ENGINE_URL/v1/databases/local-nebula/check"
# Continue once reachable: true. Credentials come from the exported local .env.

./library.sh create '{"name":"knowledge-library"}'
./sources.sh create knowledge-library '{
  "name":"knowledge-text","database_id":"local-milvus",
  "collection_name":"my_knowledge_text_gme"
}'
./sources.sh create knowledge-library '{
  "name":"knowledge-graph","database_id":"local-nebula",
  "collection_name":"my_knowledge_concepts"
}'
./pools.sh create knowledge-library '{
  "id":"knowledge-documents","name":"Knowledge",
  "sources":["knowledge-text","knowledge-graph"]
}'
./assets.sh add knowledge-library \
  ../data/okf/my_dataset/corpus ../data/okf/my_dataset/okf_bundle \
  --pool knowledge-documents --wait
```

After both sources finish syncing, inspect the graph:

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
curl -sS "$ENGINE_URL/v1/libraries/my-library/assets/$ASSET_ID/enrichment" \
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

- Repeat `--pool` to search several pools. Raw vector scores are not calibrated
  across models; use separate pools to inspect model rankings independently.
- OKF results are document chunks with graph traces, not generated answers.
  Missing document chunks usually mean the full corpus is absent, its paths
  changed, or text sync has not finished.

For source replacement, deletion and other operations, see the
[API reference](../api.md) or each CLI script's `--help`.

## Appendix: inspect data with web UIs (for dev)

### Milvus (Attu)

Milvus has no built-in UI. Attu is its web console, and its version must match Milvus. This stack runs Milvus v2.4.x, so use Attu v2.4.x. The `latest` tag only connects to Milvus 2.6 and later.

```bash
docker run -d --name attu --restart unless-stopped \
  --network data-intelligence-network -p 33000:3000 zilliz/attu:v2.4.12
```

Open `http://<host>:33000` and connect with address `milvus-standalone:19530` and authentication **None**.
Use the container-network service name, not `localhost`.
Your collection (`my_library_video_xclip`) holds one 512-dimension record per supported video clip/segment.

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
  from `NEBULA_USERNAME` and password from `NEBULA_PASSWORD` in your local `.env`.
  Do not use `localhost` or a `nebula://` prefix.
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

The console is at `http://<host>:9001`. Sign in with `MINIO_ROOT_USER` and
`MINIO_ROOT_PASSWORD` from your local `.env`. Use deployment-specific credentials
for any shared environment.
Ports come from `MINIO_API_PORT` and `MINIO_CONSOLE_PORT` in `data-intelligence-engine/deployment/docker/.env`.

This MinIO is Milvus's internal storage. `a-bucket` holds Milvus segment files and index data, not your videos.
By default the engine keeps content records on the filesystem under `data-intelligence-engine/workspace/content/`, and the videos stay in `data-intelligence-engine/workspace/uploads/`:

```bash
ls data-intelligence-engine/workspace/content/*/assets    # one JSON content record per asset
ls data-intelligence-engine/workspace/uploads             # the video files themselves
```

## Appendix: replace a source

A source's model and parameters are fixed at creation. Another checkpoint or
weight variant means a new source naming a different prepared model ID, replacing
the old one in its pool. No re-ingest is needed; old vectors stay until deleted.

Example: switch to the separately prepared `xclip-base-patch16-zero-shot-fp16`
package under the model root (prepare it first, see [below](#appendix-convert-x-clip-before-use)):

The package needs its own `config.json`, tokenizer files and both IR towers;
copying only the XML/BIN pairs is insufficient.

Check which source covers each kind of content before the switch:
```bash
./pools.sh routing my-library video-segments
```

```bash
# 1. New source. embedding_model selects the prepared package directory.
./sources.sh create my-library '{
  "name":"video-xclip-fp16",
  "database_id":"local-milvus",
  "collection_name":"my_library_video_xclip_fp16",
  "operator_options":{"asset_types":["video"],"embedding_model":"xclip-base-patch16-zero-shot-fp16"}
}'

# 2. Attach it, replacing video-xclip-embedding
./pools.sh add-sources my-library video-segments video-xclip-fp16 --replaces video-xclip-embedding

# 3. Watch the switch
./pools.sh read my-library video-segments \
  | jq '.source_statuses[] | {source_id, status, serving_state}'
```

Check the routing again afterwards -- the new source should now answer for `short_video`:
```bash
./pools.sh routing my-library video-segments
```

- While the new source is `PREPARING`, the pool keeps answering from the old one.
- Once it has re-embedded every asset, it becomes `SERVING` and the old one becomes `DEPRECATED` -- its vectors stay in Milvus, its model is unloaded.
- Rollback is the same command in the other direction: `--replaces video-xclip-fp16` with `video-xclip-embedding` attached again.

The console shows `serving_state` per pool in the Sources list and canvas
inspector. Choose `DEPRECATED` to stop that binding, or `SERVING` to resume it;
its stored vectors are kept. A resumed source behind the pool reports `PREPARING`
until ready. This does not replace or stop another source; use `--replaces` above
for coordinated replacement. Removing a canvas link instead detaches the binding.

Even weight variants of the same checkpoint can produce different scores; the
new source rebuilds vectors before taking over. The same procedure applies to a
different checkpoint. X-CLIP's `frames_per_clip` must match the selected package's
checkpoint; a mismatch is refused at attach.

The same works for images: prepare a separate
`gme-Qwen2-VL-2B-Instruct-OV-int4` package, create a source with
`"embedding_model":"gme-Qwen2-VL-2B-Instruct-OV-int4"`, then replace
`image-gme-embeddings`.

## Appendix: convert X-CLIP before use

From the repository root, download the checkpoint once and export the variants:

```bash
cd data-intelligence-engine
huggingface-cli download microsoft/xclip-base-patch16-zero-shot \
  --local-dir workspace/models/xclip-base-patch16-zero-shot

python scripts/xclip/convert.py \
  --model workspace/models/xclip-base-patch16-zero-shot --precision fp32

python scripts/xclip/convert.py \
  --model workspace/models/xclip-base-patch16-zero-shot --precision fp16 \
  --out workspace/models/xclip-base-patch16-zero-shot-fp16
```

`convert.py` writes both XML/BIN towers and copies the checkpoint configuration,
tokenizer and preprocessing files into the output directory. Original PyTorch
weights are not copied. The source checkpoint must already contain these files;
the converter reports missing files before conversion.

- Without `--out`, output goes to `<model>/openvino/<precision>/`.
- With `--out` above, the complete fp16 runtime package is directly under
  `workspace/models/xclip-base-patch16-zero-shot-fp16/`. Select it with
  `"embedding_model":"xclip-base-patch16-zero-shot-fp16"`.
- Conversion is a preparation step; the engine only loads the resulting package.

Optional: compare the fp16 export against the original PyTorch checkpoint:

```bash
python scripts/xclip/verify.py \
  --model workspace/models/xclip-base-patch16-zero-shot \
  --ir workspace/models/xclip-base-patch16-zero-shot-fp16
```

Where every model goes, and how to convert or check it: [How to prepare embedding models](how-to-prepare-models.md).

## Appendix: delete ingested data

Deleting a pool, source or library only removes the engine's configuration, not
its external vectors or stored files. Delete assets first to remove their indexed
records and stored content. The engine has no API to drop a Milvus collection.

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
./assets.sh delete-one my-library "<asset-name-or-id>"
```

For several, put `{"asset_ids": ["<id>", "<id>"]}` in a file and run `./assets.sh delete my-library @file.json`.
Find ids with `./pools.sh assets my-library video-segments`.
Re-ingesting a deleted file works as a fresh ingest, but deleting the asset removed the file from `uploads/`, so stage it again with `assets.sh create`.
A file you ingested from an absolute path outside `uploads/` is left in place.

### Remove everything for one library

**Order matters:** assets first (including unassigned assets), then all pools,
all sources, and the library. Stop ingestion/enrichment writes first.
These calls go through the engine API and leave external collections/spaces intact:

```bash
# From data-intelligence-engine/scripts. List every asset, including unassigned ones, and
# delete them all with {"asset_ids": [...]} in a file.
./assets.sh read my-library
./assets.sh delete my-library @asset-ids.json
# Then each pool, each source, and the library.
./pools.sh delete my-library video-segments
./sources.sh delete my-library video-xclip-embedding
./library.sh delete my-library
```

To remove the now-empty Milvus collection as well, use Attu or `pymilvus`:

```bash
python - <<'PY'
from pymilvus import MilvusClient
MilvusClient(uri="http://localhost:19530").drop_collection("my_library_video_xclip")
PY
```

The engine-owned media files are already removed with their assets. External
input files are kept; empty content directories may remain.

### Reset the whole dev environment

**Destructive:** removes configuration, database data, content and uploads for
every library; keeps `models/`. Stop the engine, then stop both database stacks
before clearing their bind-mounted data. Run from the repository root:

```bash
docker compose -f data-intelligence-engine/deployment/docker/docker-compose-milvus.yml down
docker compose -f data-intelligence-engine/deployment/docker/docker-compose-nebula.yml down
sudo find data-intelligence-engine/workspace -mindepth 2 -maxdepth 2 \
  ! -path 'data-intelligence-engine/workspace/models/*' -exec rm -rf {} +
```

The `find` command clears the contents of every top-level directory under
`data-intelligence-engine/workspace/` except `models/`, including hidden entries. Directory shells and top-level files
are kept; top-level symlinks are not followed. `sudo` is needed for container-owned
files. These commands have not been run against the live environment.

Start the services again using [Start the services](#2-start-the-services).

## Appendix: the engine workspace (for dev)

Everything the engine keeps lives under `data-intelligence-engine/workspace/`. Know who writes each directory before you clean one up.

| Directory | What is in it | Written by | Read by |
|---|---|---|---|
| `configs/` | `asset_library.json` (libraries, sources, pools, assets) and `databases.json` (connections) | the engine, on every change | the engine at startup |
| `content/<library-id>/assets/` | one JSON content record per asset: its metadata, caption and a pointer to the media | the engine at ingest, and again when a caption arrives | the engine when it indexes, captions and retrieves |
| `content/<library-id>/blobs/` | bytes with no file of their own, named by SHA-256. Today that is only the figures extracted from a PDF | the engine at ingest | the engine when it embeds a figure |
| `uploads/` | the files you ingest. **For a video, image or audio file this is the asset itself**, not a staging copy | `assets.sh` (it copies your file here), or a service that uploads files for the engine | the engine: ingest, embedding and captioning open the file here directly |
| `milvus/{etcd,minio,db}` | Milvus metadata, segment files and local data | the Milvus containers (compose bind mounts) | Milvus only |
| `models/` | embedding, reranker, X-CLIP and GME model files | you, or the `convert.py` scripts under `data-intelligence-engine/scripts/` | the engine when it loads a model |

A video, image or audio file is not copied into the content store. Its block points at the file with a `file://` path, and the engine opens that path
for embedding and captioning. So a file in `uploads/` (or at the absolute path you gave) must stay where it is as long as its asset exists.
If you move or delete it, re-indexing and captioning fail with `origin file is gone`.

Deleting an asset deletes its file when the file is inside `uploads/`. A file you pointed at elsewhere is never deleted by the engine; the response lists it under `files_kept`.