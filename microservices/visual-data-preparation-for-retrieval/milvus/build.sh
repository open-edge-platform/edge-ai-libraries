#!/bin/bash

# Build script for Milvus DataPrep docker image.
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

PUSH=false

# Build and optionally push the dataprep-visualdata-milvus image.
#
# The script refreshes the local wheel dependency before docker build:
# - Rebuilds the multimodal-embedding-serving wheel from its source tree.
# - Copies the freshly built wheel into ./wheels/.
# - Updates src/requirements.txt wheel reference if the version changed.

usage() {
  cat <<'EOF'
Usage: ./build.sh [--push]

Options:
  --push          Push the built image to the configured registry after a successful build
  --help          Show this help message and exit

Environment variables:
  REGISTRY        Optional registry prefix (e.g. "intel/"). Trailing slash is handled automatically.
  TAG             Image tag (default: latest)
  IMAGE_NAME      Image name without registry/tag (default: dataprep-visualdata-milvus)
  http_proxy      Optional proxy forwarded to docker build as build-arg (same for https_proxy/no_proxy).
EOF
}

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) log_error "Unknown option: $1"; usage; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MICROSERVICES_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
EMBEDDING_DIR="$MICROSERVICES_DIR/multimodal-embedding-serving"
WHEELS_DIR="$SCRIPT_DIR/src/wheels"
DOCKERFILE="$SCRIPT_DIR/src/Dockerfile"
REQUIREMENTS_FILE="$SCRIPT_DIR/src/requirements.txt"

[[ -d "$EMBEDDING_DIR" ]] || { log_error "Cannot find multimodal embedding service at $EMBEDDING_DIR"; exit 1; }
[[ -f "$DOCKERFILE" ]] || { log_error "Cannot find Dockerfile at $DOCKERFILE"; exit 1; }
[[ -f "$REQUIREMENTS_FILE" ]] || { log_error "Cannot find requirements.txt at $REQUIREMENTS_FILE"; exit 1; }
mkdir -p "$WHEELS_DIR"

if ! command -v poetry >/dev/null 2>&1; then
  log_error "poetry is required to build the multimodal embedding wheel."
  exit 1
fi

log_info "Building multimodal embedding wheel from $(basename "$EMBEDDING_DIR")"
rm -rf "$EMBEDDING_DIR/dist"
(
  cd "$EMBEDDING_DIR"
  poetry build --format wheel >/dev/null
)
WHEEL_SOURCE="$(find "$EMBEDDING_DIR/dist" -maxdepth 1 -type f -name 'multimodal_embedding_serving-*.whl' | sort | tail -n 1)"
if [[ -z "$WHEEL_SOURCE" ]]; then
  log_error "Wheel build failed; no wheel found in $EMBEDDING_DIR/dist"
  exit 1
fi
WHEEL_BASENAME="$(basename "$WHEEL_SOURCE")"
rm -f "$WHEELS_DIR"/multimodal_embedding_serving-*.whl
cp "$WHEEL_SOURCE" "$WHEELS_DIR/"
# Absolute container path so pip resolves it regardless of cwd inside docker RUN.
WHEEL_REL_PATH="/home/user/dataprep/src/wheels/$WHEEL_BASENAME"
log_info "Copied $WHEEL_BASENAME to $WHEELS_DIR"

# Keep requirements.txt wheel reference aligned with whichever wheel version was just built.
CURRENT_WHEEL_LINE="$(grep -E '^/home/user/dataprep/src/wheels/multimodal_embedding_serving-.+\.whl$' "$REQUIREMENTS_FILE" || true)"
if [[ -z "$CURRENT_WHEEL_LINE" ]]; then
  log_error "Unable to locate multimodal_embedding_serving wheel reference in $REQUIREMENTS_FILE"
  exit 1
fi
if [[ "$CURRENT_WHEEL_LINE" != "$WHEEL_REL_PATH" ]]; then
  log_warn "Updating wheel reference in requirements.txt: $CURRENT_WHEEL_LINE -> $WHEEL_REL_PATH"
  sed -E -i 's|^/home/user/dataprep/src/wheels/multimodal_embedding_serving-.+\.whl$|'"$WHEEL_REL_PATH"'|' "$REQUIREMENTS_FILE"
fi

REGISTRY=${REGISTRY:-}
TAG=${TAG:-latest}
IMAGE_NAME=${IMAGE_NAME:-dataprep-visualdata-milvus}
[[ -n "$REGISTRY" ]] && REGISTRY="${REGISTRY%/}/"
FULL_IMAGE="${REGISTRY}${IMAGE_NAME}:${TAG}"

log_info "Building docker image ${FULL_IMAGE}"

BUILD_ARGS=()
for proxy_var in http_proxy https_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY; do
  if [[ -n "${!proxy_var:-}" ]]; then
    BUILD_ARGS+=("--build-arg" "${proxy_var}=${!proxy_var}")
  fi
done

if docker buildx version &>/dev/null; then
  export DOCKER_BUILDKIT=1
fi

# Dockerfile COPY uses path `visual-data-preparation-for-retrieval/milvus`, so
# the build context must be the parent `microservices` directory.
set -x
docker build "${BUILD_ARGS[@]}" -t "$FULL_IMAGE" -f "$DOCKERFILE" "$MICROSERVICES_DIR"
set +x

log_info "Successfully built $FULL_IMAGE"

if $PUSH; then
  if [[ -z "$REGISTRY" ]]; then
    log_warn "REGISTRY not set; skipping docker push."
  else
    log_info "Pushing $FULL_IMAGE"
    set -x
    docker push "$FULL_IMAGE"
    set +x
  fi
fi
