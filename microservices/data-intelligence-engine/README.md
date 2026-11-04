# Data Intelligence Engine

- [Description](#description)
- [Quick Start](#quick-start)
  - [Docker](#docker)
    - [When attaching a source fails](#when-attaching-a-source-fails)
  - [Local Development](#local-development)

## Description

Data Intelligence Engine is a standalone FastAPI service for asset-library
management, content ingestion, retrieval, reranking, and runtime database
management. It listens on port `16022` by default.

```text
ingest:   files/text -> normalized content blocks -> vector or graph projections
retrieve: query -> document fusion or media search -> optional reranking -> chunks
```

An asset library owns assets, storage sources, and the pools that materialize
selected assets into those sources. Database connections are registered through
the API and persisted in the engine workspace rather than fixed in environment
configuration.

The Python project is rooted here and uses a flat `src/` layout:

```text
data-intelligence-engine/
|-- pyproject.toml
|-- src/
|   |-- api/
|   |-- assetlib/
|   |-- core/
|   |-- databasehub/
|   |-- console/
|   `-- main.py
|-- deployment/
|-- scripts/
|-- tests/
`-- workspace/
```

Documentation:

- [Get started](docs/get-start.md)
- [API reference](docs/api.md)
- [User guide](docs/user-guide.md)
- [Text-to-media retrieval and media reranking](docs/text-to-media-retrieval.md)
- [API script examples](scripts/README.md)

## Quick Start

### Docker

From the repository root, start the bundled Milvus stack and the engine;
NebulaGraph is needed only for OKF concept graphs. All services use the existing
shared `data-intelligence-network` so other services on it can reach them.

Prepare model artifacts before starting the engine: it never downloads models
or exports checkpoints at runtime. Place the prepared files under
`data-intelligence-engine/workspace/models` (mounted as `/workspace/models`), or the configured
`ENGINE_MODEL_ROOT_PATH`. See the
[model preparation guide](docs/how-to-guides/how-to-prepare-models.md)
for embedding, reranking, video, speech, and layout preparation. Missing or
incomplete models produce an explicit error when their capability is used.

The engine runs embedding and reranking on the GPU by default, which needs the
container user to be in the groups that own `/dev/dri`. Every Compose setting
has a default, so `deployment/docker/.env` only needs the values that differ per
host: on a first deployment, write the group IDs and MinIO data owner from the
current host. Keep an existing `.env` when upgrading; it is git-ignored and may
contain credentials.

```bash
cd data-intelligence-engine/deployment/docker
if [ ! -f .env ]; then
  cat > .env <<EOF
VIDEOGROUPID=$(getent group video | cut -d: -f3)
RENDERGROUPID=$(getent group render | cut -d: -f3)
MINIO_UID=$(id -u)
MINIO_GID=$(id -g)
EOF
fi
mkdir -p ../../workspace/milvus/{etcd,minio,db}
```

Set a non-default `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` in `.env` before
production use. Compose passes the same credentials to MinIO and Milvus; changing
only one service's environment would break storage access. A one-shot
`minio-init` service hands the MinIO data directory to `MINIO_UID:MINIO_GID`
before MinIO starts, so the stack comes up whoever owns that directory and
whether or not the UID exists on the host. Setting the IDs to your own keeps
the data deletable without `sudo`. On hosts without a
usable GPU, set both `ENGINE_DOC_EMBEDDING_DEVICE` and `ENGINE_RERANK_DEVICE` to `CPU`.

Then bring the required stacks up (NebulaGraph is optional, for OKF only).
Building the engine image fetches apt and PyPI packages, so behind a corporate
proxy the build must be told about it. `up` cannot pass build args, so build the
image first with the host's proxy forwarded, then start everything (the
`--build-arg NAME` form with no value passes the value from the current
environment; harmless when the variables are unset):

```bash
docker network inspect "${ENGINE_NETWORK:-data-intelligence-network}" >/dev/null 2>&1 \
  || docker network create "${ENGINE_NETWORK:-data-intelligence-network}"
docker compose -f docker-compose-milvus.yml up -d
# Optional, only for OKF concept graphs:
docker compose -f docker-compose-nebula.yml up -d
docker compose build \
  --build-arg http_proxy --build-arg https_proxy --build-arg no_proxy \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY
docker compose up -d
curl "http://localhost:${ENGINE_PORT:-16022}/health"
```

Builds require Docker BuildKit (the default with current Docker Compose).
Dependencies are installed in a layer keyed by `pyproject.toml`, before copying
source, so code-only rebuilds reuse the installed packages. The engine itself is
then installed without dependency resolution, build isolation, or index access.
BuildKit also retains pip's download cache outside the image, so dependency
changes can reuse cached downloads. The optional OKF extractor uses the same
approach with its `requirements.txt`. Compose embeds inline
cache metadata in each Python service image and imports that image as a cache
source; on a new builder, pull a previously built image first to reuse its layers.
The first build populates the caches. Avoid `--no-cache` and build-cache pruning
for routine rebuilds; base-image or build-instruction changes can invalidate
otherwise unchanged dependency layers.

If the network or host port is customized in `.env`, export the same
`ENGINE_NETWORK` / `ENGINE_PORT` values for shell commands; Compose reads `.env`
itself, but the shell does not. `ENGINE_CONTAINER_PORT`
controls the internal listener and healthcheck independently of the host port.
All runtime `ENGINE_*` settings in the [configuration reference](docs/user-guide.md#configuration)
can be set in `.env`; unspecified values use the defaults in `src/config.py`.

All model capabilities share `ENGINE_MODEL_ROOT_PATH`, defaulting to
`$ENGINE_WORKSPACE/models` (`/workspace/models` in Compose). Set it to the parent
directory containing your model folders; model IDs determine their subdirectories.
Document embedding uses `ENGINE_DOC_EMBEDDING_*`. Each source can select its own
prepared model with `operator_options.embedding_model` under the shared root.

A fresh workspace has no database registrations. Register the bundled Milvus so
pools have somewhere to index to. A content store is optional — without one,
asset content goes to `$ENGINE_WORKSPACE/content` through a registration the
engine writes down on first use — but register one explicitly to choose where it
goes or to share it between deployments:

```bash
curl -X POST http://localhost:16022/v1/databases \
  -H 'Content-Type: application/json' \
  -d '{
    "id":"local-milvus",
    "type":"vector",
    "backend":"milvus",
    "options":{"uri":"http://milvus-standalone:19530"}
  }'

curl -X POST http://localhost:16022/v1/databases \
  -H 'Content-Type: application/json' \
  -d '{
    "id":"local-content",
    "type":"object",
    "backend":"filesystem",
    "options":{"root":"/workspace/content"}
  }'

curl -X POST \
  http://localhost:16022/v1/databases/local-milvus/check
```

Open [http://localhost:16022/console/](http://localhost:16022/console/). To stop all services while preserving
workspace state:

```bash
docker compose down
docker compose -f docker-compose-nebula.yml down
docker compose -f docker-compose-milvus.yml down
```

#### When attaching a source fails

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
  the devices are passed through but not readable, which is the `.env` group ids
  above being absent or wrong. Confirm with:

  ```bash
  docker exec data-intelligence-engine python3 -c \
    "import openvino as ov; print(ov.Core().available_devices)"
  ```

  A GPU-capable PTL host should report `GPU` and not just `['CPU']`. Fix `.env`
  and `docker compose up -d` to recreate the container. Setting
  `ENGINE_DOC_EMBEDDING_DEVICE=CPU` and `ENGINE_RERANK_DEVICE=CPU` is the fallback
  if the host has no usable GPU.

### Local Development

Data Intelligence Engine requires Python 3.11 or newer. From `data-intelligence-engine/`, create a
virtual environment and install the project. The extra index supplies the pinned
CPU-only PyTorch wheels declared in `pyproject.toml`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[test]' \
  --extra-index-url https://download.pytorch.org/whl/cpu
data-intelligence-engine
```

A fresh workspace starts with no database registrations. Register a reachable
Milvus instance using `http://localhost:19530`, then open the console. A
filesystem content store at an absolute writable path is optional; content goes
to the workspace store otherwise. Existing registrations and libraries are
restored from `ENGINE_WORKSPACE/configs` at startup.

Run the test suite from the standalone project root:

```bash
python3 -m pytest
```

Configuration is environment-driven. `ENGINE_WORKSPACE` defaults to
`data-intelligence-engine/workspace`; container deployments set it to `/workspace`. See the
[user guide](docs/user-guide.md#configuration) for all settings and the
[API reference](docs/api.md) for the complete HTTP surface.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## License

Licensed under the [Apache License 2.0](LICENSE).
