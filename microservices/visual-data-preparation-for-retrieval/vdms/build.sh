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
# The script refreshes the local wheel dependency metadata before docker build:
# - Updates pyproject.toml wheel path if the wheel filename/version changes.
# - Updates poetry.lock hash for multimodal-embedding-serving.

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
WHEELS_DIR="$SCRIPT_DIR/wheels"
DOCKERFILE="$SCRIPT_DIR/docker/Dockerfile"
PYPROJECT_FILE="$SCRIPT_DIR/pyproject.toml"
LOCK_FILE="$SCRIPT_DIR/poetry.lock"

[[ -d "$EMBEDDING_DIR" ]] || { log_error "Cannot find multimodal embedding service at $EMBEDDING_DIR"; exit 1; }
[[ -f "$DOCKERFILE" ]] || { log_error "Cannot find Dockerfile at $DOCKERFILE"; exit 1; }
[[ -f "$PYPROJECT_FILE" ]] || { log_error "Cannot find pyproject.toml at $PYPROJECT_FILE"; exit 1; }
[[ -f "$LOCK_FILE" ]] || { log_error "Cannot find poetry.lock at $LOCK_FILE"; exit 1; }
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
WHEEL_DEST="$WHEELS_DIR/$WHEEL_BASENAME"
WHEEL_REL_PATH="wheels/$WHEEL_BASENAME"
log_info "Copied $WHEEL_BASENAME to $WHEELS_DIR"

# Keep pyproject wheel path aligned with whichever wheel version was just built.
CURRENT_WHEEL_PATH="$(grep -E '^multimodal-embedding-serving = \{path = "wheels/.+\.whl"\}$' "$PYPROJECT_FILE" | sed -E 's/^.*path = "([^"]+)".*$/\1/' || true)"
if [[ -z "$CURRENT_WHEEL_PATH" ]]; then
  log_error "Unable to locate multimodal-embedding-serving wheel dependency in $PYPROJECT_FILE"
  exit 1
fi

if [[ "$CURRENT_WHEEL_PATH" != "$WHEEL_REL_PATH" ]]; then
  log_warn "Updating wheel dependency path in pyproject.toml: $CURRENT_WHEEL_PATH -> $WHEEL_REL_PATH"
  sed -E -i 's|^multimodal-embedding-serving = \{path = "wheels/[^"]+\.whl"\}$|multimodal-embedding-serving = {path = "'"$WHEEL_REL_PATH"'"}|' "$PYPROJECT_FILE"
fi

# Refresh lock metadata for local wheel dependencies so Poetry hash checks pass.
log_info "Refreshing poetry.lock for multimodal-embedding-serving"
(
  cd "$SCRIPT_DIR"
  poetry update multimodal-embedding-serving --lock >/dev/null
)

WHEEL_HASH="sha256:$(sha256sum "$WHEEL_DEST" | awk '{print $1}')"
LOCKED_HASH="$(grep -A 20 '^name = "multimodal-embedding-serving"$' "$LOCK_FILE" | grep -m 1 -oE 'sha256:[0-9a-f]+' || true)"
if [[ "$LOCKED_HASH" != "$WHEEL_HASH" ]]; then
  log_error "poetry.lock hash mismatch after refresh (expected $WHEEL_HASH, found ${LOCKED_HASH:-<none>})"
  exit 1
fi
log_info "Validated poetry.lock hash for $WHEEL_BASENAME"

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
docker build "${BUILD_ARGS[@]}" --target prod -t "$IMAGE_NAME" -f "$DOCKERFILE" "$SCRIPT_DIR"
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