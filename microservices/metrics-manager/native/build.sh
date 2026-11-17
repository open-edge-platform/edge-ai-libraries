#!/bin/sh
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Builds the bare-metal Metrics Manager .deb.
#
# The collectors, Telegraf and qmassa are lifted out of the container image
# rather than compiled again here. That is the point: the package and the image
# then ship byte-identical binaries, so a reading that differs between the two
# deployments cannot be blamed on a different build. mm-tui is the exception —
# the image has no reason to carry a terminal dashboard, so it is compiled
# directly, with the same pinned toolchain the image uses.
#
# Usage:
#     ./build.sh                 # build the image if needed, then the package
#     SKIP_IMAGE_BUILD=1 ./build.sh
#
# The result is written to native/packaging/dist/.

set -eu

NATIVE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPONENT_DIR=$(CDPATH= cd -- "$NATIVE_DIR/.." && pwd)
REPO_ROOT=$(CDPATH= cd -- "$COMPONENT_DIR/../.." && pwd)
PACKAGING_DIR="$NATIVE_DIR/packaging"
STAGE_DIR="$PACKAGING_DIR/dist"

# versions.env is the single source of truth for every third-party pin; see the
# header of that file.
# shellcheck source=/dev/null
. "$COMPONENT_DIR/versions.env"

VERSION=$(tr -d '[:space:]' <"$COMPONENT_DIR/VERSION")
IMAGE=${IMAGE:-metrics-manager:$VERSION}

say() {
    printf '==> %s\n' "$1"
}

# ---------------------------------------------------------------------------
# 1. Container image
# ---------------------------------------------------------------------------
# The image is where the collectors get compiled and where Telegraf and qmassa
# get fetched and checksummed, so it has to exist and be current before
# anything can be copied out of it.

if [ "${SKIP_IMAGE_BUILD:-0}" = "1" ]; then
    say "reusing $IMAGE without rebuilding"
    if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        echo "build.sh: $IMAGE does not exist; unset SKIP_IMAGE_BUILD" >&2
        exit 1
    fi
else
    say "building $IMAGE"
    COMPOSE_PROGRESS=plain make -C "$COMPONENT_DIR" build
fi

image_version=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$IMAGE")
if [ "$image_version" != "$VERSION" ]; then
    echo "build.sh: $IMAGE reports version '$image_version'; rebuild with TAG=$VERSION before packaging" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Staging
# ---------------------------------------------------------------------------

say "staging artefacts in $STAGE_DIR"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/bin" "$STAGE_DIR/doc"

container=$(docker create "$IMAGE")
# The container is only a handle for docker cp; remove it whatever happens.
trap 'docker rm --force "$container" >/dev/null 2>&1 || true' EXIT INT TERM

docker cp "$container:/usr/bin/telegraf" "$STAGE_DIR/bin/telegraf"
docker cp "$container:/usr/local/bin/qmassa" "$STAGE_DIR/bin/qmassa"
for plugin in mm-plugin-cpu mm-plugin-gpu mm-plugin-npu mm-plugin-proc mm-plugin-membw mm-plugin-rapl; do
    docker cp "$container:/usr/libexec/metrics-manager/$plugin" "$STAGE_DIR/bin/$plugin"
done

docker rm --force "$container" >/dev/null
trap - EXIT INT TERM

# ---------------------------------------------------------------------------
# 3. The terminal dashboard
# ---------------------------------------------------------------------------
# Built statically so the package depends on nothing beyond the two libraries
# qmassa needs.

say "compiling mm-tui with $GO_IMAGE"
docker run --rm \
    -v "$NATIVE_DIR":/src \
    -v "$STAGE_DIR/bin":/out \
    -w /src \
    -u "$(id -u):$(id -g)" \
    -e CGO_ENABLED=0 \
    -e GOFLAGS=-mod=readonly \
    -e GOCACHE=/tmp/gocache \
    -e GOMODCACHE=/tmp/gomod \
    -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
    -e http_proxy -e https_proxy -e no_proxy \
    "$GO_IMAGE" \
    go build -trimpath -ldflags "-s -w -X main.version=$VERSION" -o /out/mm-tui ./cmd/mm-tui

chmod 0755 "$STAGE_DIR"/bin/*

# ---------------------------------------------------------------------------
# 4. Documentation and licences
# ---------------------------------------------------------------------------

say "collecting documentation and licences"
# The packaged README is the published user guide, staged rather than copied to
# a second location, so the page on the documentation site and the one in
# /usr/share/doc cannot drift apart.
cp "$COMPONENT_DIR/docs/user-guide/get-started/bare-metal-package.md" \
    "$STAGE_DIR/doc/README.md"
cp "$COMPONENT_DIR/docs/user-guide/get-started/native-metric-migration.md" \
    "$STAGE_DIR/doc/native-metric-migration.md"
cp "$COMPONENT_DIR/docs/user-guide/get-started/terminal-dashboard.md" \
    "$STAGE_DIR/doc/terminal-dashboard.md"
cp -R "$COMPONENT_DIR/docs/user-guide/get-started/images" "$STAGE_DIR/doc/images"
cp "$REPO_ROOT/LICENSE" "$STAGE_DIR/doc/LICENSE"

# The third-party listing is generated rather than maintained by hand so that
# it cannot drift from go.mod. The module list comes from the toolchain itself.
{
    cat "$PACKAGING_DIR/doc/third_party_header.txt"
    printf '\nTelegraf %s\n    https://github.com/influxdata/telegraf\n    MIT License\n' \
        "$TELEGRAF_VERSION"
    printf '\nqmassa %s\n    https://github.com/ulissesf/qmassa\n    MIT License\n' \
        "$QMASSA_VERSION"
    printf '\nGo modules linked into mm-tui and the collector plugins:\n\n'
    docker run --rm \
        -v "$NATIVE_DIR":/src -w /src \
        -u "$(id -u):$(id -g)" \
        -e GOFLAGS=-mod=readonly \
        -e GOCACHE=/tmp/gocache -e GOMODCACHE=/tmp/gomod \
        -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
        -e http_proxy -e https_proxy -e no_proxy \
        "$GO_IMAGE" \
        go list -m -f '    {{.Path}} {{.Version}}' all |
        grep -v '^    github.com/open-edge-platform/'
} >"$STAGE_DIR/doc/third_party_program.txt"

# ---------------------------------------------------------------------------
# 5. The package
# ---------------------------------------------------------------------------

say "building the package with $NFPM_IMAGE"
docker run --rm \
    -v "$PACKAGING_DIR":/work \
    -w /work \
    -u "$(id -u):$(id -g)" \
    -e METRICS_MANAGER_VERSION="$VERSION" \
    "$NFPM_IMAGE" \
    package --config nfpm.yaml --packager deb --target /work/dist

package=$(find "$STAGE_DIR" -maxdepth 1 -name '*.deb' -print -quit)
if [ -z "$package" ]; then
    echo "build.sh: nfpm produced no package" >&2
    exit 1
fi

say "built $package"
