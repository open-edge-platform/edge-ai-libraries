#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# One-click start on a clean host: workspace, .env, image, models (GME and the
# reranker by default), Milvus and the engine, then the Milvus registration.
# The image is built only when missing or with --build, and the models are
# prepared only with --model or --models, so a rerun just starts the services.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: quickstart.sh [options]

Options:
  --build           Rebuild the engine image (it is always built when missing)
  --model           Prepare the default models: GME and the reranker
  --models "LIST"   Prepare these models instead; see prepare-models.sh --help.
                    For every multimodal how-to section: "gme reranker layout xclip whisper media-reranker-int8"
  --gpu             Keep Compose's GPU defaults for embedding and reranking (default: CPU)
  -h, --help        Show this help

First run: quickstart.sh --model

HF_ENDPOINT, http_proxy, https_proxy and no_proxy are passed to the image build
and to the model downloads.
EOF
}

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
DOCKER_DIR="$ENGINE_DIR/deployment/docker"

models="gme reranker"
use_gpu=false
build=false
prepare=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build) build=true ;;
    --model) prepare=true ;;
    --models) models="${2:?--models needs a value}"; prepare=true; shift ;;
    --gpu) use_gpu=true ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

for tool in docker curl jq; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required"
done
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 (docker compose) is required"

cd "$DOCKER_DIR"

# --- workspace: created by this user, writable by the engine container (UID 1000)
log "Preparing the workspace"
workspace="$ENGINE_DIR/workspace"
mkdir -p "$workspace"/{models,uploads,configs,content} "$workspace"/milvus/{etcd,minio,db}
if [[ "$(id -u)" != 1000 ]]; then
  for dir in "$workspace" "$workspace"/{models,uploads,configs,content}; do
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
env_value() { sed -n "s/^$1=//p" .env | tail -n 1; }
port="$(env_value ENGINE_PORT)"
network="$(env_value ENGINE_NETWORK)"
image="$(env_value ENGINE_IMAGE)"
ENGINE_URL="http://localhost:${port:-16022}"
network="${network:-data-intelligence-network}"
image="${image:-data-intelligence-engine:latest}"

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
elif [[ -z "$(ls -A "$workspace/models")" ]]; then
  log "warning: $workspace/models is empty; rerun with --model to prepare the models"
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
backend="$(jq -r '.backend' <<<"$embedding")"
model_id="$(jq -r '.model_id' <<<"$embedding")"
if [[ "$backend" != openai_compatible ]]; then
  if [[ "$model_id" == *gme* && "$backend" != native_openvino_gme ]]; then
    die "document embedding model $model_id needs ENGINE_DOC_EMBEDDING_BACKEND=native_openvino_gme, but the engine runs $backend.
Unset the variable in this shell (unset ENGINE_DOC_EMBEDDING_BACKEND) or fix it in deployment/docker/.env, then rerun this script.
Sources created meanwhile keep $backend; create them again after the restart."
  fi
  ready="$(jq -r --arg id "$model_id" '[.models[] | select(.name == $id) | .ready] | any' <<<"$embedding")"
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
data-intelligence-engine/docs/get-start.md.
EOF
