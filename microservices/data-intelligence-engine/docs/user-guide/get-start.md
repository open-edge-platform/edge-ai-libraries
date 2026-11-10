# Get Started

- **Time to Complete:** about 25 minutes, most of it the first model download
- **Programming Language:** Python

Deploy the Data Intelligence Engine with Milvus, ingest a text file, and
retrieve it.

## Prerequisites

- Docker with Docker Compose v2 ([Installation Guide](https://docs.docker.com/engine/install/ubuntu/)),
  `curl` and `jq`.
- About 50 GB of free disk for the image, all default models and their downloaded
  originals (which can be deleted afterwards); less with `--models` (Step 1).
- Access to Hugging Face for the first run. Behind a proxy, export
  `http_proxy`/`https_proxy` and configure the Docker daemon's proxy. For users
  based in PRC, you might need to set `export HF_ENDPOINT=https://hf-mirror.com`.

WMF/EMF pictures in DOCX/PPTX files are rendered with LibreOffice, which the
Docker image includes. To build without it, export `INSTALL_LIBREOFFICE=false`
before the first run (or before rebuilding the image); those pictures are then
skipped and the rest of the file is still ingested. Native Debian/Ubuntu
installations need `libreoffice-draw-nogui` and `fonts-dejavu-core`.

If you are cloning from the larger monorepo and only need this service, you
can use sparse checkout:

```bash
git clone --filter=blob:none --sparse https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries
git sparse-checkout set microservices/data-intelligence-engine
cd microservices/data-intelligence-engine
```

## Step 1: Deploy

```bash
bash scripts/quickstart.sh
```

The first run builds the image, downloads and prepares **all** default models
(GME, bge-reranker-large, PP-DocLayoutV3, ViCLIP-B, Whisper and the Qwen3-VL
INT8 media reranker) under `workspace/models`, starts Milvus and the engine on
port `16022`, and registers Milvus as `local-milvus`. Later runs only start the
services.

If you do not want all the models, name the ones to prepare with `--models` on
the first run. The text ingestion and retrieval in this guide need only GME,
which embeds both the file and the query, so this is enough to run every step
below:

```bash
bash scripts/quickstart.sh --models "gme"
```

Prepare the other models later with `scripts/prepare-models.sh` when you ingest
PDFs, images, videos or audio.

The image is built only when it is missing, so after changing the engine source,
rebuild it; the engine container is recreated from the new image. To stop and
remove the services, keeping the data and models, use `--down`. Run
`bash scripts/quickstart.sh --help` for the other options.

```bash
bash scripts/quickstart.sh --build
bash scripts/quickstart.sh --down
```

Check the engine:

```bash
cd scripts
./status.sh health
```

```json
{
  "service": "engine",
  "status": "ok",
  "workspace": "/workspace",
  "databases": 1,
  "asset_libraries": 0
}
```

### Databases

Database connections are registered at runtime through the API, not set in a
configuration file. This guide needs no registration of its own:

- `quickstart.sh` registered Milvus as `local-milvus`
  (`http://milvus-standalone:19530`); that is the `"databases": 1` above, and the
  source in Step 2 uses it.
- The first ingest registers `workspace-content`, a filesystem store under
  `workspace/content` that keeps the ingested content.

List the registrations with `./databases.sh read`. Each backend takes these
`options`:

| `type` / `backend` | `options`, with addresses as the engine container sees them |
|---|---|
| `vector` / `milvus` | `uri` (required), e.g. `http://milvus-standalone:19530`; other keys, such as `token` or `db_name`, go to the Milvus client |
| `graph` / `nebula` | `url` (required), e.g. `nebula://nebula-graphd:9669`; optional `username` (default `root`), `password` and `space` |
| `object` / `filesystem` | `root` (required), a directory inside the container, e.g. `/workspace/content` |

## Step 2: Ingest a File

Write a sample file:

```bash
cat > /tmp/edge-notes.txt <<'EOF'
Intel Edge AI Libraries provide microservices for building AI applications at the edge.
The Data Intelligence Engine ingests documents, images, videos and audio, embeds them
with OpenVINO models, stores the vectors in Milvus and serves retrieval over HTTP.
EOF
```

Create a library, a source that indexes into Milvus with the default text model,
and a pool that binds them; then ingest the file. `--wait` returns once the file
is indexed:

```bash
./library.sh create '{"name":"demo"}'
./sources.sh create demo '{"name":"docs","database_id":"local-milvus","collection_name":"demo_docs"}'
./pools.sh create demo '{"id":"docs","name":"Docs","sources":["docs"]}'
./assets.sh add demo /tmp/edge-notes.txt --pool docs --wait
```

To ingest more kinds of files (PDFs, images, videos, audio or OKF knowledge
bundles), follow [How to ingest multimodal data](how-to-guides/how-to-ingest-mm-data.md).

## Step 3: Retrieve

```bash
./retrieve.sh query demo "Where are the vectors stored?" --pool docs --top-k 3 \
  | jq '.chunks[] | {score, file: .metadata.file_name, text}'
```

Example result:

```json
{
  "score": 0.24457761645317078,
  "file": "edge-notes.txt",
  "text": "Intel Edge AI Libraries provide microservices for building AI applications at the edge.\nThe Data Intelligence Engine ingests documents, images, videos and audio, embeds them\nwith OpenVINO models, stores the vectors in Milvus and serves retrieval over HTTP."
}
```

Without the `jq` filter, each chunk also carries its `metadata` (asset, source,
pool and rank). The same search is `POST /v1/retrieve`; the web console at
[http://localhost:16022/console/](http://localhost:16022/console/) runs it too.

## Learn More

- [How to ingest multimodal data](how-to-guides/how-to-ingest-mm-data.md) — PDFs,
  images, videos, audio, OKF, status checks and media reranking.
- [How to prepare models](how-to-guides/how-to-prepare-models.md).
- [User guide](user-guide.md) — concepts, configuration and troubleshooting.
- [API reference](api.md).
- [Skills for agent](../../skills/README.md) — let an OpenClaw agent query this
  retrieval through the `knowledgebase` skill.
