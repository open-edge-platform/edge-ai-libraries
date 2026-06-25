#!/bin/bash

# Build script for VDMS DataPrep docker image.
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

PUSH=false

# Build and optionally push the vdms-dataprep image.
#
# The docker build uses the microservices directory as context so the local
# multimodal-embedding-serving source path dependency is available in-image.

usage() {
  cat <<'EOF'
Usage: ./build.sh [--push]

Options:
  --push          Push the built image to the configured registry after a successful build
  --help          Show this help message and exit

Environment variables:
  REGISTRY_URL    Optional registry prefix. Trailing slash is handled automatically.
  PROJECT_NAME    Optional project namespace. Trailing slash is handled automatically.
  TAG             Image tag (default: latest)
  http_proxy      Optional proxy forwarded to docker build as build-arg (same for https_proxy/no_proxy).
EOF
}

log_info() {
  echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      PUSH=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      log_error "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MICROSERVICES_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
EMBEDDING_DIR="$MICROSERVICES_DIR/multimodal-embedding-serving"
DOCKERFILE="$SCRIPT_DIR/docker/Dockerfile"

[[ -d "$EMBEDDING_DIR" ]] || { log_error "Cannot find multimodal embedding service at $EMBEDDING_DIR"; exit 1; }
[[ -f "$DOCKERFILE" ]] || { log_error "Cannot find Dockerfile at $DOCKERFILE"; exit 1; }

REGISTRY_URL=${REGISTRY_URL:-}
PROJECT_NAME=${PROJECT_NAME:-}
TAG=${TAG:-latest}
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"
REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"
IMAGE_NAME="${REGISTRY}vdms-dataprep:${TAG}"

log_info "Building docker image ${IMAGE_NAME}"

BUILD_ARGS=()
for proxy_var in http_proxy https_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY; do
  if [[ -n "${!proxy_var:-}" ]]; then
    BUILD_ARGS+=("--build-arg" "${proxy_var}=${!proxy_var}")
  fi
done

# Enable BuildKit if available for efficient multi-stage builds.
# Falls back to legacy builder if buildx is not installed - the Dockerfile stage
# ordering ensures prod builds correctly with either builder.
if docker buildx version &>/dev/null; then
  export DOCKER_BUILDKIT=1
fi
set -x
docker build "${BUILD_ARGS[@]}" --target prod -t "$IMAGE_NAME" -f "$DOCKERFILE" "$MICROSERVICES_DIR"
set +x

log_info "Successfully built $IMAGE_NAME"

if $PUSH; then
  if [[ -z "$REGISTRY" ]]; then
    log_warn "Registry not configured; skipping docker push."
  else
    log_info "Pushing $IMAGE_NAME"
    set -x
    docker push "$IMAGE_NAME"
    set +x
  fi
fi