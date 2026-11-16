#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# One-click start on a clean host: workspace, .env, image, models (by default
# every model the ingest guide uses: GME, the text reranker, PP-DocLayoutV3,
# ViCLIP-B, Whisper and the Qwen3-VL INT8 media reranker), Milvus and the
# engine, then the Milvus registration.
# The image is built only when missing or with --build, and the models are
# prepared on the first run (an empty model root) or with --model or --models,
# so a rerun just starts the services. --down stops and removes them again.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: quickstart.sh [options]

Options:
  --build           Rebuild the engine image (it is always built when missing)
  --model           Prepare the default models:
                    "gme reranker layout viclip-b whisper media-reranker-int8"
  --models "LIST"   Prepare these models instead; see prepare-models.sh --help
  --gpu             Keep Compose's GPU defaults for embedding and reranking (default: CPU)
  --down            Stop and remove the engine and Milvus containers and the
                    network; the workspace (data and models) is kept
  -h, --help        Show this help

First run: quickstart.sh (the default models are prepared when none are in place)

HF_ENDPOINT, http_proxy, https_proxy and no_proxy are passed to the image build
and to the model downloads. localhost is added to no_proxy, since the script
talks to the engine through it.
EOF
}

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
DOCKER_DIR="$ENGINE_DIR/deployment/docker"

models="gme reranker layout viclip-b whisper media-reranker-int8"
use_gpu=false
build=false
prepare=false
down=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build) build=true ;;
    --model) prepare=true ;;
    --models) models="${2:?--models needs a value}"; prepare=true; shift ;;
    --gpu) use_gpu=true ;;
    --down) down=true ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# The engine is reached through localhost; a proxy must not get those requests.
export no_proxy="localhost,127.0.0.1${no_proxy:+,$no_proxy}"
export NO_PROXY="localhost,127.0.0.1${NO_PROXY:+,$NO_PROXY}"

command -v docker >/dev/null 2>&1 || die "docker is required"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 (docker compose) is required"

cd "$DOCKER_DIR"

# A value exported in this shell wins over .env, as it does for Compose.
env_value() {
  local exported="${!1:-}"
  if [[ -n "$exported" ]]; then printf '%s' "$exported"; return; fi
  [[ -f .env ]] && sed -n "s/^$1=//p" .env | tail -n 1
  return 0
}
network="$(env_value ENGINE_NETWORK)"
network="${network:-data-intelligence-network}"

if [[ "$down" == true ]]; then
  log "Stopping and removing the engine and Milvus"
  docker compose down --remove-orphans
  docker compose -f docker-compose-milvus.yml down --remove-orphans
  if docker network inspect "$network" >/dev/null 2>&1; then
    docker network rm "$network" >/dev/null \
      || log "warning: network $network is still in use by: $(docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' "$network")"
  fi
  log "Stopped. The workspace is kept: $ENGINE_DIR/workspace"
  exit 0
fi

for tool in curl jq; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required"
done

# --- workspace: created by this user, writable by the engine container (UID 1000)
log "Preparing the workspace"
workspace="$ENGINE_DIR/workspace"
# hf_models too: once the workspace belongs to UID 1000, prepare-models.sh run
# by another user could not create it.
mkdir -p "$workspace"/{models,hf_models,uploads,configs,content} "$workspace"/milvus/{etcd,minio,db}
if [[ "$(id -u)" != 1000 ]]; then
  for dir in "$workspace" "$workspace"/{models,hf_models,uploads,configs,content}; do
    [[ "$(stat -c %u "$dir")" == 1000 ]] || sudo chown 1000:1000 "$dir"
  done
fi

# --- .env: host-specific values only; an existing file is kept
if [[ ! -f .env ]]; then
  log "Writing deployment/docker/.env"
  {
    video_gid="$(getent group video | cut -d: -f3 || true)"
    render_gid="$(getent group render | cut -d: -f3 || true)"
    [[ -n "$video_gid" ]] && echo "VIDEOGROUPID=$video_gid"
    [[ -n "$render_gid" ]] && echo "RENDERGROUPID=$render_gid"
    echo "MINIO_UID=$(id -u)"
    echo "MINIO_GID=$(id -g)"
  } > .env
fi
if [[ "$use_gpu" == false ]]; then
  # An existing .env may lack a final newline; appending would join two lines.
  [[ -z "$(tail -c 1 .env)" ]] || echo >> .env
  for key in ENGINE_DOC_EMBEDDING_DEVICE ENGINE_RERANK_DEVICE; do
    grep -q "^$key=" .env || echo "$key=CPU" >> .env
  done
fi
port="$(env_value ENGINE_PORT)"
image="$(env_value ENGINE_IMAGE)"
ENGINE_URL="http://localhost:${port:-16022}"
image="${image:-data-intelligence-engine:latest}"
# Compose maps the GPU device into the engine; a host without one would refuse
# to start the container, so CPU mode maps an always-present device instead.
if [[ -z "$(env_value ENGINE_GPU_DEVICE)" && ! -e /dev/dri ]]; then
  [[ "$use_gpu" == false ]] || die "--gpu needs a GPU device (/dev/dri), and this host has none"
  export ENGINE_GPU_DEVICE=/dev/null
fi
# A first run prepares the default models unasked: without them the engine
# starts and only fails later. Not for a remote embedding service, which
# needs no local model. Checked before the (long) image build.
if [[ "$prepare" == false && -z "$(ls -A "$workspace/models")" \
      && "$(env_value ENGINE_DOC_EMBEDDING_BACKEND)" != remote_openai_compatible ]]; then
  log "$workspace/models is empty; the default models ($models) will be prepared"
  prepare=true
fi
if [[ "$prepare" == true ]]; then
  hub="${HF_ENDPOINT:-https://huggingface.co}"
  curl -fsS -m 30 -o /dev/null "$hub" 2>/dev/null \
    || die "cannot reach $hub to download the models. Set the proxy variables, or HF_ENDPOINT to a reachable mirror, and rerun"
fi

# --- network, image, models
docker network inspect "$network" >/dev/null 2>&1 || {
  log "Creating Docker network $network"
  docker network create "$network" >/dev/null
}
# Built here rather than left to `docker compose up`, which would build a
# missing image without the proxy arguments.
docker image inspect "$image" >/dev/null 2>&1 || build=true
if [[ "$build" == true ]]; then
  log "Building the engine image"
  docker compose build \
    --build-arg http_proxy --build-arg https_proxy --build-arg no_proxy \
    --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY
fi
if [[ "$prepare" == true ]]; then
  # shellcheck disable=SC2086  # the model list is word-split on purpose
  ENGINE_IMAGE="$image" "$SCRIPTS_DIR/prepare-models.sh" $models
fi

# --- services
log "Starting Milvus"
docker compose -f docker-compose-milvus.yml up -d
milvus="$(env_value MILVUS_CONTAINER_NAME)"
milvus="${milvus:-milvus-standalone}"
for _ in $(seq 1 60); do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "$milvus" 2>/dev/null)" == healthy ]] && break
  sleep 5
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$milvus" 2>/dev/null)" == healthy ]] \
  || die "Milvus did not become healthy; see: docker ps -a --filter name=milvus"
log "Starting the engine"
# Compose prefers variables exported in this shell over its own defaults and
# .env, so a value left over from another setup silently changes the models.
overrides="$(env | grep -E '^ENGINE_[A-Z_]*(EMBEDDING|RERANK)[A-Z_]*=' | sed -E 's/(API_KEY=).*/\1***/' | sort || true)"
if [[ -n "$overrides" ]]; then
  printf 'Model settings exported in this shell override docker-compose.yml:\n%s\n' "$overrides"
fi
docker compose up -d
for _ in $(seq 1 60); do
  curl -fsS "$ENGINE_URL/health" >/dev/null 2>&1 && break
  sleep 5
done
curl -fsS "$ENGINE_URL/health" >/dev/null 2>&1 \
  || die "the engine did not become healthy; see: docker logs data-intelligence-engine"

# --- the document embedding model must be prepared and run on its backend:
# otherwise sources are created fine and only attaching one to a pool fails.
embedding="$(curl -fsS "$ENGINE_URL/v1/models/embedding")"
document_embedding="$(jq -c '.defaults.document // .' <<<"$embedding")"
backend="$(jq -r '.backend // empty' <<<"$document_embedding")"
model_id="$(jq -r '.model_id // empty' <<<"$document_embedding")"
model_path="$(jq -r '.model_path // empty' <<<"$document_embedding")"
[[ -n "$backend" && -n "$model_id" ]] \
  || die "the engine did not report a document embedding backend and model in /v1/models/embedding."
if [[ "$backend" != remote_openai_compatible ]]; then
  ready="$(jq -r --arg id "$model_id" --arg path "$model_path" '
    any(.models[]?; .ready == true and
      (if $path != "" then .path == $path else .name == $id or .path == $id end))
  ' <<<"$embedding")"
  [[ "$ready" == true ]] || die "document embedding model $model_id is not prepared under $ENGINE_DIR/workspace/models.
Prepare it (for GME: $SCRIPTS_DIR/prepare-models.sh gme) and rerun this script."
fi

# --- Milvus registration, persisted in the workspace
milvus_uri="http://milvus-standalone:19530"
registered_uri="$(curl -fsS "$ENGINE_URL/v1/databases/local-milvus" 2>/dev/null | jq -r '.options.uri // empty' || true)"
if [[ -z "$registered_uri" ]]; then
  log "Registering Milvus as local-milvus"
  curl -fsS -X POST "$ENGINE_URL/v1/databases" -H 'Content-Type: application/json' \
    -d "{\"id\":\"local-milvus\",\"type\":\"vector\",\"backend\":\"milvus\",
         \"options\":{\"uri\":\"$milvus_uri\"}}" >/dev/null
elif [[ "$registered_uri" != "$milvus_uri" ]]; then
  # An older registration (for example from a host-run engine) is not changed
  # silently: other sources may rely on it.
  die "local-milvus is already registered with $registered_uri, which the engine container may not reach.
To point it at this Milvus, run and then rerun this script:
  curl -X PATCH $ENGINE_URL/v1/databases/local-milvus -H 'Content-Type: application/json' -d '{\"options\":{\"uri\":\"$milvus_uri\"}}'"
fi
reachable=false
for _ in $(seq 1 24); do
  if curl -fsS -X POST "$ENGINE_URL/v1/databases/local-milvus/check" | jq -e '.reachable' >/dev/null 2>&1; then
    reachable=true
    break
  fi
  sleep 5
done
[[ "$reachable" == true ]] || die "local-milvus is not reachable from the engine; check: docker ps --filter name=milvus"

log "Ready"
cat <<EOF
  Engine:   $ENGINE_URL  (health: $ENGINE_URL/health)
  Console:  $ENGINE_URL/console/
  Milvus:   registered as local-milvus
  Models:   $ENGINE_DIR/workspace/models
Next: create a library, a source and a pool, then ingest; see
data-intelligence-engine/docs/user-guide/get-start.md.
EOF
