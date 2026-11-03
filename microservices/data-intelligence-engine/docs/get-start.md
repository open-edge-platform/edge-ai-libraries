# How to ingest multimodal data

Ingest videos, images, audio, illustrated PDFs or an OKF knowledge-graph bundle and search them with a text query. A video segment of up to 60 seconds becomes one embedding, with no chunking; longer videos are stored but not embedded by the default video model. An audio file is transcribed in the background, and its transcript is what gets embedded. PDFs produce text chunks and fused illustration embeddings; an OKF bundle adds concepts and links grounded in a separately ingested document corpus.

Ingest returns `202` with `status: "materializing"` before extraction or embedding finishes, without a `warnings` field. Poll the asset listing until the returned IDs exist and their `materialization` is `ready`, then inspect each media asset's `/enrichment`: `embedding_status: "no_source"` and `embedding_reason` explain unsupported media or missing coverage. Pool readiness alone does not mean that captioning or transcription has finished.

```text
segment.mp4 ──► engine ──► X-CLIP video encoder ──► Milvus
image.jpg   ──► engine ──► GME image encoder    ──► Milvus
speech.wav  ──► engine ──► Whisper ──► transcript ──► GME text encoder ──► Milvus
                                                   ▲
text query ──► engine ──► the same model's text encoder ──┘  nearest matches
```

The query is embedded separately for each serving source: X-CLIP's text encoder
searches video vectors, while GME's text encoder searches image and transcript
vectors. These retrieval scores are not comparable across models; the optional
media reranker can order candidates from different sources together.

## Contents

- [One-click start](#one-click-start)
- [Prerequisites](#prerequisites)
- [Start the services](#start-the-services)
- [Ingest videos](#ingest-videos)
- [Ingest images](#ingest-images)
- [Ingest audio](#ingest-audio)
- [Ingest PDFs](#ingest-pdfs)
- [Ingest OKF](#ingest-okf)
  - [Start and register NebulaGraph](#start-and-register-nebulagraph)
  - [Create the sources and pool](#create-the-sources-and-pool)
  - [Ingest the complete corpus and bundle](#ingest-the-complete-corpus-and-bundle)
  - [Retrieve the documents through the graph](#retrieve-the-documents-through-the-graph)
- [Retrieve](#retrieve)
- [Media reranking](#media-reranking)
- [Next: several models, upgrades and rollback](#next-several-models-upgrades-and-rollback)
- [Notes](#notes)
- [Appendix: inspect data with web UIs (for dev)](#appendix-inspect-data-with-web-uis-for-dev)
  - [Milvus (Attu)](#milvus-attu)
  - [NebulaGraph (Studio)](#nebulagraph-studio)
  - [MinIO](#minio)
- [Appendix: replace a source](#appendix-replace-a-source)
- [Appendix: convert X-CLIP to fp16](#appendix-convert-x-clip-to-fp16)
- [Appendix: delete ingested data](#appendix-delete-ingested-data)
  - [Remove some assets](#remove-some-assets)
  - [Remove everything for one library](#remove-everything-for-one-library)
  - [Reset the whole dev environment](#reset-the-whole-dev-environment)
- [Appendix: the engine workspace (for dev)](#appendix-the-engine-workspace-for-dev)

## One-click start

`data-intelligence-engine/scripts/quickstart.sh` takes a clean host to a running engine.
It needs Docker with Docker Compose v2, `curl` and `jq`. In order, it:

1. creates `data-intelligence-engine/workspace` and writes `deployment/docker/.env` (an existing
   file is kept),
2. creates the shared Docker network and builds the engine image when it is
   missing (or always, with `--build`),
3. with `--model` or `--models`, prepares the models with `prepare-models.sh`
   (GME and bge-reranker-large by default; see
   [How to prepare models](how-to-guides/how-to-prepare-models.md)),
4. starts Milvus and the engine and waits until they are healthy,
5. registers Milvus as `local-milvus`.

```bash
cd data-intelligence-engine/scripts
./quickstart.sh --model                                          # first run: GME + reranker
./quickstart.sh --models "gme reranker layout xclip whisper media-reranker-int8"  # every section of this guide
./quickstart.sh                                                  # later runs: just start the services
./quickstart.sh --build                                          # after changing the engine source
```

| Option | Values | Description |
|---|---|---|
| `--build` | — | Rebuild the engine image; without it the image is built only when missing |
| `--model` | — | Prepare the default models, GME and bge-reranker-large |
| `--models` | Space-separated list of `gme`, `reranker`, `media-reranker`, `media-reranker-int8`, `layout`, `xclip`, `whisper`, `bge` | Prepare these models instead of the default ones |
| `--gpu` | — | Keep Compose's GPU defaults for document embedding and reranking; without it both run on CPU |

Models are prepared only when asked for, and `prepare-models.sh` skips any
model already in place, so add more later with `--models`. The other steps are
skipped when already done, so you can rerun the script.
`HF_ENDPOINT` and the proxy variables are passed to the image build and the
model downloads. When it finishes, continue with any ingest section whose
models you prepared: the default models cover [Ingest images](#ingest-images)
and [Ingest OKF](#ingest-okf). The next two sections,
[Prerequisites](#prerequisites) and [Start the services](#start-the-services),
do the same as the script, manually.

## Prerequisites

The engine, Milvus and NebulaGraph all run as containers. You need:

- Docker with Docker Compose v2, `curl` and `jq`. No Python environment is needed
  on the host.
- Your data in a folder, for example `data/videos/my_video_segments/`,
  `data/mmdir/my_pdfs/` or `data/okf/my_dataset/` in this project directory. Replace
  the example paths and file names below with your own. `data/` is git-ignored.
  The scripts upload your files through the engine API, so the engine container
  does not need access to this folder.
- The models for the content you ingest, prepared under `data-intelligence-engine/workspace/models`
  before you create the sources. Follow
  [How to prepare models](how-to-guides/how-to-prepare-models.md), which runs every download
  and conversion in a throwaway engine container:

  | Section below | Models |
  |---|---|
  | [Ingest videos](#ingest-videos) | X-CLIP |
  | [Ingest images](#ingest-images) | GME |
  | [Ingest audio](#ingest-audio) | Whisper and GME |
  | [Ingest PDFs](#ingest-pdfs) | GME and PP-DocLayoutV3 |
  | [Ingest OKF](#ingest-okf) | GME |

> **Model Card:**
> microsoft/xclip-base-patch16-zero-shot is a base-sized X-CLIP model (ViT-B/16) trained on Kinetics-400 using 32 frames per video at 224×224 resolution. It extends CLIP to video-language understanding via contrastive learning on (video, text) pairs, making it suitable for zero-shot/few-shot video classification and video-text retrieval. It achieves zero-shot top-1 accuracy of 44.6% on HMDB-51, 72.0% on UCF-101, and 65.2% on Kinetics-600.

## Start the services

Run from the `data-intelligence-engine/` directory. Create the workspace as your own user first;
if Docker creates it for a bind mount, root owns it and the engine cannot write
to it. The engine container runs as UID 1000, so if `id -u` prints something
else, also run
`sudo chown 1000:1000 workspace workspace/{models,uploads,configs,content}`.

Compose reads `deployment/docker/.env`. Write it once with this host's GPU group
IDs and MinIO owner; drop the two `*_DEVICE` lines on a host with a usable Intel
GPU, because Compose runs document embedding and reranking on the GPU by default.
To use a remote embedding server instead of local GME, see
[Remote document embedding](user-guide.md#remote-document-embedding).

```bash
mkdir -p workspace/{models,uploads,configs,content} workspace/milvus/{etcd,minio,db}
cd deployment/docker
cat > .env <<EOF
VIDEOGROUPID=$(getent group video | cut -d: -f3)
RENDERGROUPID=$(getent group render | cut -d: -f3)
MINIO_UID=$(id -u)
MINIO_GID=$(id -g)
ENGINE_DOC_EMBEDDING_DEVICE=CPU
ENGINE_RERANK_DEVICE=CPU
EOF
docker compose build \
  --build-arg http_proxy --build-arg https_proxy --build-arg no_proxy \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY
docker network inspect data-intelligence-network >/dev/null 2>&1 \
  || docker network create data-intelligence-network
docker compose -f docker-compose-milvus.yml up -d
docker compose up -d
until curl -fsS http://localhost:16022/health; do sleep 5; done; echo
cd ../..
```

Engine settings such as `ENGINE_ASR_LANGUAGE` go in `deployment/docker/.env`.
After changing `.env`, run `docker compose up -d` in `deployment/docker` again to
recreate the engine container.

Register Milvus once. The engine container reaches it by its service name, and
the engine persists the registration in its workspace:

```bash
curl -X POST http://localhost:16022/v1/databases -H 'Content-Type: application/json' -d '{
  "id":"local-milvus","type":"vector","backend":"milvus",
  "options":{"uri":"http://milvus-standalone:19530"}}'
curl -X POST http://localhost:16022/v1/databases/local-milvus/check
```

A library holds assets, a source says where vectors go, and a pool binds assets to sources. Run the `*.sh` commands below from `data-intelligence-engine/scripts`.

```bash
cd scripts
./library.sh create '{"name":"my-library"}'
```

All ingest examples below return after the server accepts the request; processing
continues in the background. Optionally append `--wait` to any `assets.sh create`
or `assets.sh add` command to have the script poll the returned asset IDs until
materialization finishes. This is a client-side convenience for every data type,
not a PDF/OKF requirement or an API request option. It does not wait for captioning
or transcription; check `/enrichment` separately for those jobs. Wait for asset
materialization and the required source statuses before running retrieval or
graph inspection.

## Ingest videos

Each video segment of up to 60 seconds is embedded whole by X-CLIP.

```bash
# Source: asset_types selects video files; the default video model (X-CLIP,
# from ENGINE_VIDEO_EMBEDDING_*) is pinned in the source's profile.
./sources.sh create my-library '{
  "name":"video-xclip-embedding",
  "database_id":"local-milvus",
  "collection_name":"my_library_video_xclip",
  "operator_options":{"asset_types":["video"]}
}'

# Pool: attaching the source loads the model, so setup errors surface here
./pools.sh create my-library '{"id":"video-segments","name":"Video Segments","sources":["video-xclip-embedding"]}'

# Ingest every .mp4 in a folder. assets.sh uploads each file through the engine API.
VIDEO_DIR=../data/videos/my_video_segments
jq -Rn '{asset_pool_ids:["video-segments"], file_paths:[inputs | select(length > 0)]}' \
  < <(find "$VIDEO_DIR" -name '*.mp4') > /tmp/ingest-videos.json
./assets.sh create my-library @/tmp/ingest-videos.json

# Ingest returns 202 with status materializing; poll asset materialization first
./assets.sh wait my-library patient_sits_up.mp4
# Then inspect source synchronization / enrichment as appropriate
./pools.sh read my-library video-segments | jq '.source_statuses[].status'
```

Or, to ingest a few files, list them:

```bash
./assets.sh create my-library '{
  "asset_pool_ids":["video-segments"],
  "file_paths":[
    "../data/videos/my_video_segments/patient_sits_up.mp4",
    "../data/videos/my_video_segments/nurse_brings_water.mp4"
  ]
}'
```

Re-ingesting a file replaces its vectors, so a repeated run creates no duplicates. If a segment is not found, `curl http://localhost:16022/v1/libraries/my-library/assets/<asset_id>/enrichment` says why: `embedding_status` is `ready`, or `no_source` with a reason.

## Ingest images

Images are embedded by GME-Qwen2-VL-2B, which puts text and images in one space, so a text query finds pictures.

```bash
# Source: asset_types selects standalone image files; the default image model
# (GME, from ENGINE_IMAGE_EMBEDDING_*) has 1536 dimensions. Optional:
# embedding_model selects a separately prepared weight variant; max_image_tokens
# is the main latency knob.
./sources.sh create my-library '{
  "name":"image-gme-embeddings",
  "database_id":"local-milvus",
  "collection_name":"my_library_image_gme",
  "operator_options":{"asset_types":["image"]}
}'

# Pool: loads the model, about 5 s on CPU with int8 weights
./pools.sh create my-library '{"id":"images","name":"Images","sources":["image-gme-embeddings"]}'

# Ingest every image in a folder; each takes about 1-2 s on CPU
IMAGE_DIR=../data/images
jq -Rn '{asset_pool_ids:["images"], file_paths:[inputs | select(length > 0)]}' \
  < <(find "$IMAGE_DIR" \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \)) \
  > /tmp/ingest-images.json
./assets.sh create my-library @/tmp/ingest-images.json

# Wait for `ready`
./pools.sh read my-library images | jq '.source_statuses[].status'
```

Or, to ingest a few files, list them:

```bash
./assets.sh create my-library '{
  "asset_pool_ids":["images"],
  "file_paths":[
    "../data/images/ward_overview.jpg",
    "../data/images/medication_cart.png",
    "../data/images/bedside_monitor.jpg"
  ]
}'
```

## Ingest audio

After ingest, Whisper transcribes each recording in the background, and GME embeds the transcript, so a text query finds what was said. Mandarin is the default; for another language, set `ENGINE_ASR_LANGUAGE` (for example `en`) in `deployment/docker/.env` and recreate the engine container.

```bash
# Source: asset_types:["audio"] selects recordings; GME embeds their transcripts
./sources.sh create my-library '{
  "name":"audio-gme",
  "database_id":"local-milvus",
  "collection_name":"my_library_audio_gme",
  "operator_options":{"asset_types":["audio"]}
}'
./pools.sh create my-library '{"id":"audio","name":"Audio","sources":["audio-gme"]}'

# Ingest every recording in a folder
AUDIO_DIR=../data/audio/my_recordings
jq -Rn '{asset_pool_ids:["audio"], file_paths:[inputs | select(length > 0)]}' \
  < <(find "$AUDIO_DIR" \( -iname '*.wav' -o -iname '*.mp3' -o -iname '*.flac' -o -iname '*.m4a' \)) \
  > /tmp/ingest-audio.json
./assets.sh create my-library @/tmp/ingest-audio.json

# An initially empty pool may already say ready. Wait for asset materialization,
# then poll enrichment until completed + ready; background extraction runs first.
./assets.sh wait my-library morning_handover.wav
curl http://localhost:16022/v1/libraries/my-library/assets/<asset_id>/enrichment \
  | jq '{transcript_status, embedding_status}'
```

Or, to ingest a few files, list them:

```bash
./assets.sh create my-library '{
  "asset_pool_ids":["audio"],
  "file_paths":[
    "../data/audio/my_recordings/morning_handover.wav",
    "../data/audio/my_recordings/ward_round.mp3"
  ]
}'
```

A recording is searchable once `transcript_status` is `completed` and `embedding_status` is `ready`. Each 30-second stretch of speech is one result, with `t_start_ms` and `t_end_ms`.

## Ingest PDFs

PDF text is indexed as chunks; extracted illustrations are embedded with their
reference text by GME.

> **Note:** Prepare the GME package and PP-DocLayoutV3 (`pp_doclayout_v3.onnx`
> under `data-intelligence-engine/workspace/models/PP-DocLayoutV3/`); see
> [How to prepare models](how-to-guides/how-to-prepare-models.md). Scanned PDFs are read with
> Tesseract, which the engine image includes with Chinese and English data.

```bash
# Source: native_openvino_gme selects the document/text pipeline.
./sources.sh create my-library '{
  "name":"pdf-gme",
  "database_id":"local-milvus",
  "collection_name":"my_library_pdf_gme",
  "operator_options":{
    "embedding_backend":"native_openvino_gme",
    "embedding_model":"gme-Qwen2-VL-2B-Instruct-OV",
    "embedding_device":"CPU",
    "asset_types":["pdf"]
  }
}'
./pools.sh create my-library '{"id":"pdf-documents","name":"PDF Documents","sources":["pdf-gme"]}'

# Ingest every PDF in a folder.
PDF_DIR=../data/mmdir/my_pdfs
jq -Rn '{asset_pool_ids:["pdf-documents"], file_paths:[inputs | select(length > 0)]}' \
  < <(find "$PDF_DIR" -type f -iname '*.pdf' | sort) > /tmp/ingest-pdfs.json
./assets.sh create my-library @/tmp/ingest-pdfs.json

# Check asset materialization, then source synchronization.
./pools.sh read my-library pdf-documents \
  | jq '.source_statuses[] | {source_id, status, serving_state, error}'
```

Or, to ingest a few files, list them:

```bash
./assets.sh create my-library '{
  "asset_pool_ids":["pdf-documents"],
  "file_paths":[
    "../data/mmdir/my_pdfs/manual.pdf",
    "../data/mmdir/my_pdfs/architecture.pdf"
  ]
}'
```

Once materialization and source synchronization are ready, search the PDF pool:

```bash
./retrieve.sh query my-library "What does the architecture diagram show?" \
  --pool pdf-documents --type vectorsimilarity --top-k 5
```

Keep this document source separate from standalone-image sources to avoid
indexing the same extracted illustration twice.

## Ingest OKF

Ingest an existing OKF concept bundle with its original documents:

```text
data/okf/my_dataset/
├── corpus/          # original documents; preserve paths referenced by source_files
│   ├── doctors/
│   ├── records/
│   └── residents/
└── okf_bundle/      # one OKF asset: index.md + concept subdirectories
    ├── index.md
    ├── doctor/
    ├── resident/
    └── ...
```

Use **Milvus** for document/concept vectors and **NebulaGraph** for concepts and
links. Keep both sources, the complete corpus and the bundle in the **same pool**
of a separate `knowledge-library`.

### Start and register NebulaGraph

After [Start the services](#start-the-services), run from `data-intelligence-engine/scripts`:

```bash
docker compose -f ../deployment/docker/docker-compose-nebula.yml up -d

# The engine container reaches Nebula by its service name on the shared network.
curl -X POST http://localhost:16022/v1/databases -H 'Content-Type: application/json' -d '{
  "id":"local-nebula","type":"graph","backend":"nebula",
  "options":{"url":"nebula://nebula-graphd:9669"}}'
curl -X POST http://localhost:16022/v1/databases/local-nebula/check
```

Wait for `reachable: true`.

> **Note:** `username` defaults to `root`, and `password` can be omitted while
> Nebula's authorization is disabled, which is this dev stack's default. If
> authorization is enabled, add valid `username` and `password` to `options`. Use
> the client port `9669`; `19669` is only for HTTP status checks.

### Create the sources and pool

```bash
./library.sh create '{"name":"knowledge-library"}'

# A document/text source for the original corpus, not a standalone-media source.
./sources.sh create knowledge-library '{
  "name":"knowledge-text",
  "database_id":"local-milvus",
  "collection_name":"my_knowledge_text_gme",
  "operator_options":{
    "embedding_backend":"native_openvino_gme",
    "embedding_model":"gme-Qwen2-VL-2B-Instruct-OV",
    "embedding_device":"CPU"
  }
}'

# Only OKF assets go into this graph source; ordinary corpus files stay in Milvus.
./sources.sh create knowledge-library '{
  "name":"knowledge-graph",
  "database_id":"local-nebula",
  "collection_name":"my_knowledge_concepts",
  "operator_options":{"asset_types":["okf"]}
}'
./pools.sh create knowledge-library '{
  "id":"knowledge-documents",
  "name":"Knowledge Documents",
  "sources":["knowledge-text","knowledge-graph"]
}'
```

### Ingest the complete corpus and bundle

```bash
OKF_DATASET=../data/okf/my_dataset

# Upload each directory intact: corpus keeps its nested relative paths;
# okf_bundle is recognized by index.md and registered as ONE OKF asset.
./assets.sh add knowledge-library \
  "$OKF_DATASET/corpus" \
  "$OKF_DATASET/okf_bundle" \
  --pool knowledge-documents

# Poll until the returned assets are registered and their materialization is ready.
./assets.sh read knowledge-library 1 1000 \
  | jq '.assets[] | {name, materialization}'
./pools.sh read knowledge-library knowledge-documents \
  | jq '.source_statuses[] | {source_id, status, serving_state, error}'
# Once all returned assets are ready and both sources report ready / SERVING / no error:
./pools.sh graph knowledge-library knowledge-documents 20
```

Upload `corpus` and `okf_bundle` separately as shown: one asset per supported
document, plus one bundle asset. Preserve paths used by `source_files`
(for example `doctors/doctor-001.md`); do not flatten files or upload only `index.md`.
Wait for asset materialization and source sync before inspection or retrieval;
`--wait` is optional as described above.

### Retrieve the documents through the graph

```bash
# Fuse the document vector, BM25 and graph arms within this knowledge pool.
./retrieve.sh query knowledge-library "Which doctor is responsible for resident 001?" \
  --pool knowledge-documents --type rrf --top-k 10 --trace

# Or inspect only the graph arm and its trace back to document chunks.
./retrieve.sh query knowledge-library "Which doctor is responsible for resident 001?" \
  --pool knowledge-documents --type graph --top-k 10
```

Results are document chunks with graph traces, not generated answers.

> **Note:** For `missing document chunks`, check that the full corpus is in the
> same pool, its paths are intact and text sync completed. Keep the uploaded
> bundle for resync/deletion. First-text-source replacement does not migrate
> graph provenance or the concept index; see [Retrieve](#retrieve).

## Retrieve

Search one pool, or combine the media pools. PDF and OKF queries are shown in
their respective ingest sections above:

```bash
# Only videos
./retrieve.sh '{"query":"a person sitting up in bed","libraries":["my-library"],"asset_pool_ids":["video-segments"],"top_k":3}'

# Only images
./retrieve.sh '{"query":"a nurse bringing a glass of water","libraries":["my-library"],"asset_pool_ids":["images"],"top_k":3}'

# Both media pools, merged by score (omit asset_pool_ids to include PDF pools too)
./retrieve.sh '{"query":"a person sitting up in bed","libraries":["my-library"],"asset_pool_ids":["video-segments","images"],"top_k":3}'
```

The same call from Python, as a retriever would make it:

```python
import httpx

def search(query: str, library: str, top_k: int = 3):
    response = httpx.post(
        "http://localhost:16022/v1/retrieve",
        json={"query": query, "libraries": [library], "top_k": top_k},
        timeout=60,
    )
    response.raise_for_status()
    return [
        (chunk["score"], chunk["metadata"]["file_name"])
        for chunk in response.json()["chunks"]
    ]

for score, name in search("a person sitting up in bed", "my-library"):
    print(f"{score:.3f}  {name}")
```

- **Results:** videos, images, transcript chunks, PDF text/illustrations, or document chunks cited by OKF concepts. `source_id` / `source_name` identify the source; `pool_id` identifies the pool.
- **Scores:** vector sources are searched independently, taking up to `top_k` candidates per source, and the source result lists are interleaved round-robin. Scores are not calibrated across models and the merged response is not a global score ranking; this is not cross-model RRF.
- **Scope:** `asset_pool_ids` selects pools, not sources. Use separate pools for separate model rankings. Document vector/BM25/graph RRF is a separate fusion mode.
- **OKF limitation:** graph retrieval uses only the first serving text source. Replacing it does **not** yet migrate graph provenance or the concept index.

## Media reranking

Run `./prepare-models.sh media-reranker-int8` from `data-intelligence-engine/scripts`, then add
`"postprocess":{"processor_type":"reranker","top_n":3}` to a media request.
`top_k` controls candidates per source; `top_n` limits the final global ranking.
Without a usable GPU, set `ENGINE_MEDIA_RERANK_DEVICE=CPU` in
`deployment/docker/.env` and recreate the engine container.
See [Media reranking](text-to-media-retrieval.md#media-reranking) for examples,
model options and failure behavior.

## Next: several models, upgrades and rollback

To route more kinds of content, change a model or its parameters, or switch a source off without losing its vectors. A common case is in the appendix below: [replace a source](#appendix-replace-a-source).

## Notes

- **Video limit:** X-CLIP does not embed segments over 60 seconds. Check `/enrichment` for missing coverage.
- **Audio language:** ASR defaults to Mandarin; for other languages set `ENGINE_ASR_LANGUAGE` in `deployment/docker/.env` and recreate the engine container.
- **GME memory:** document and image sources share a runtime only with the same model package and device. Compose defaults to document GPU / image CPU; align devices to avoid loading two copies.
- **Model errors:** if attaching a source returns `503`, check the error for missing model files or incorrect paths.
- **Captions:** optional video captioning is not yet verified end to end. Without `ENGINE_VIDEO_SUMMARY_BASE_URL`, `caption_status: skipped` is expected.

## Appendix: inspect data with web UIs (for dev)

### Milvus (Attu)

Milvus has no built-in UI. Attu is its web console, and its version must match Milvus. This stack runs Milvus v2.4.x, so use Attu v2.4.x. The `latest` tag only connects to Milvus 2.6 and later.

```bash
docker run -d --name attu --restart unless-stopped \
  --network data-intelligence-network -p 33000:3000 zilliz/attu:v2.4.12
```

Open `http://<host>:33000` and connect with address `milvus-standalone:19530` and authentication **None**.
Use the container-network service name, not `localhost`.
Your collection (`my_library_video_xclip`) holds one 512-dimension record per video segment, with the fields above.

### NebulaGraph (Studio)

- **Start:** Studio is a separate web console. Studio v3.8.0 supports this stack's
  NebulaGraph v3.6.0. [Start NebulaGraph](#start-and-register-nebulagraph) first,
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

A source's model and parameters are fixed at creation. Changing them -- another checkpoint, another precision -- means a new source that replaces the old one in its pool. No downtime, no re-ingest, and the old vectors stay until you delete them.

Example: switch the video source from fp32 to fp16 (the fp16 IR halves the disk footprint; convert it first, see [below](#appendix-convert-x-clip-to-fp16)):

Check which source covers each kind of content before the switch:
```bash
./pools.sh routing my-library video-segments
```

```bash
# 1. New source. embedding_model selects the standalone fp16 package.
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

Switching precision does not change what the vectors mean, so results are unchanged. Switching to a different checkpoint (`embedding_model`) is a real model change -- same procedure, but expect different scores. Some parameters are fixed by the model itself: X-CLIP's `frames_per_clip` must match the checkpoint, and a source that disagrees is refused at attach.

The same works for the image source: prepare a separate INT4 package such as
`gme-Qwen2-VL-2B-Instruct-OV-int4`, select it with `embedding_model`, and replace
`image-gme-embeddings`. `operator_options.precision` is not accepted; weight
variants are selected by their prepared model ID.

## Appendix: convert X-CLIP to fp16

The engine never converts a model itself. [How to prepare models](how-to-guides/how-to-prepare-models.md)
converts X-CLIP at fp32. To create a standalone fp16 package, run the same
converter with `--precision fp16` and a separate `--out` directory from the
`data-intelligence-engine/` directory. It reads the original checkpoint from `HF_MODEL_DIR`; if
you have deleted it, download it again with step 1 of that guide's X-CLIP
section:

```bash
HF_MODEL_DIR=${HF_MODEL_DIR:-$PWD/workspace/hf_models}
OV_MODEL_DIR=${OV_MODEL_DIR:-$PWD/workspace/models}
docker run --rm -v "$HF_MODEL_DIR:/hf:ro" -v "$OV_MODEL_DIR:/ov" -v "$PWD:/engine:ro" \
  --entrypoint python data-intelligence-engine:latest \
  /engine/scripts/xclip/convert.py --model /hf/xclip-base-patch16-zero-shot \
  --out /ov/xclip-base-patch16-zero-shot-fp16 --precision fp16
# -> $OV_MODEL_DIR/xclip-base-patch16-zero-shot-fp16/
```

- Select the package with `operator_options.embedding_model`; the public
  `operator_options.precision` option is rejected.
- **fp32** IR is about 720 MB and **fp16** about 360 MB. fp16 compresses the weights on save; the graph is unchanged, and switching precisions does not require re-ingesting the original files -- the replacement source re-embeds them before taking over.

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
./sources.sh delete $LIB video-xclip-embedding
./library.sh delete $LIB

# 4. The now-empty Milvus collection, dropped with the pymilvus in the engine image
docker exec data-intelligence-engine python -c 'from pymilvus import MilvusClient
MilvusClient(uri="http://milvus-standalone:19530").drop_collection("my_library_video_xclip")'

# 5. The library's content directory (the records are already gone; this clears leftovers)
docker exec data-intelligence-engine rm -rf "/workspace/content/${CONTENT_ID:?}"
```

Skip step 4 or 5 to keep the empty collection or the content directory. The media files were already removed with their assets in step 1 if they were in `uploads/`.
Dropping a collection from Attu's Collections page does the same as step 4.

### Reset the whole dev environment

This removes every library, every vector and all uploads. It keeps the prepared models.
The commands were assembled from the steps above and have not been run as one sequence.

```bash
cd data-intelligence-engine
docker compose -f deployment/docker/docker-compose.yml down
docker compose -f deployment/docker/docker-compose-milvus.yml down
sudo sh -c 'rm -rf workspace/milvus/*/* workspace/content/* workspace/uploads/* workspace/configs/*.json'
```

The shell is started by `sudo` so the globs expand as root: Milvus's `etcd` and `minio` folders are not readable by your user, and the engine container writes as UID 1000.
Only the contents are removed, so the folders stay, and you do not need to repeat the `mkdir` from [Start the services](#start-the-services).
Start the services again from there.

## Appendix: the engine workspace (for dev)

Everything the engine keeps lives under `data-intelligence-engine/workspace/`, mounted into the engine container as `/workspace`. Know who writes each directory before you clean one up.

| Directory | What is in it | Written by | Read by |
|---|---|---|---|
| `configs/` | `asset_library.json` (libraries, sources, pools, assets) and `databases.json` (connections) | the engine, on every change | the engine at startup |
| `content/<library-id>/assets/` | one JSON content record per asset: its metadata, caption and a pointer to the media | the engine at ingest, and again when a caption arrives | the engine when it indexes, captions and retrieves |
| `content/<library-id>/blobs/` | bytes with no file of their own, named by SHA-256. Today that is only the figures extracted from a PDF | the engine at ingest | the engine when it embeds a figure |
| `uploads/<library-id>/` | the files you ingest. **For a video, image or audio file this is the asset itself**, not a staging copy | the engine, when `assets.sh` or another client uploads a file through the API | the engine: ingest, embedding and captioning open the file here directly |
| `milvus/{etcd,minio,db}` | Milvus metadata, segment files and local data | the Milvus containers (compose bind mounts) | Milvus only |
| `models/` | embedding, reranker, layout, X-CLIP, Whisper and GME model files | you, following [How to prepare models](how-to-guides/how-to-prepare-models.md) | the engine when it loads a model |

A video, image or audio file is not copied into the content store. Its block points at the file with a `file://` path, and the engine opens that path
for embedding and captioning. So a file in `uploads/` (or at the absolute path you gave) must stay where it is as long as its asset exists.
If you move or delete it, re-indexing and captioning fail with `origin file is gone`.

Deleting an asset deletes its file when the file is inside `uploads/`. A file you pointed at elsewhere is never deleted by the engine; the response lists it under `files_kept`.
