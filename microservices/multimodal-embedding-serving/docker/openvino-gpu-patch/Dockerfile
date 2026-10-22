# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Overlay image: the standard multimodal-embedding-serving image with the
# OpenVINO GPU plugin rebuilt from the 2026.4.1 release plus the GME patch set
# in patches/openvino-2026.4.1 (applied in the order listed in `series`).
#
# The Python runtime is the official openvino 2026.4.1 wheel, so the patched
# plugin is built from exactly the same release and simply replaces the wheel's
# libopenvino_intel_gpu_plugin.so; no runtime code or environment changes.
#
# Build from the microservice root, after building the standard image:
#   docker build -f docker/openvino-gpu-patch/Dockerfile \
#       -t multimodal-embedding-serving:gme-gpu-patch .
# See docs/user-guide/gme-gpu-optimization.md.

ARG BASE_IMAGE=multimodal-embedding-serving:latest

# Ubuntu 24.04 (glibc 2.39) is a supported OpenVINO build host and is not newer
# than the Debian trixie runtime base (glibc 2.41), so the plugin loads there.
FROM ubuntu:24.04 AS gpu-plugin-builder

ARG OPENVINO_TAG="2026.4.1"
ARG OPENVINO_COMMIT="e213a14725769a6a2bf86fc86650aa78a9c05d3e"
# Parallel compile jobs; empty means one per CPU. Each job can take 2-3 GB of
# RAM, so lower this on small build hosts.
ARG BUILD_JOBS=""
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --branch "${OPENVINO_TAG}" --depth 1 https://github.com/openvinotoolkit/openvino.git /openvino && \
    test "$(git -C /openvino rev-parse HEAD)" = "${OPENVINO_COMMIT}" && \
    git -C /openvino submodule update --init --recursive --jobs 8

RUN /openvino/install_build_dependencies.sh && rm -rf /var/lib/apt/lists/*

COPY docker/openvino-gpu-patch/patches/openvino-2026.4.1/ /patches/
RUN set -e; \
    while read -r patch; do \
        [ -n "$patch" ] || continue; \
        echo "Applying $patch"; \
        git -C /openvino apply --check "/patches/$patch"; \
        git -C /openvino apply "/patches/$patch"; \
    done < /patches/series

# Configure after every patch is applied: opt-6 adds a source file.
RUN cmake -S /openvino -B /openvino/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DENABLE_INTEL_GPU=ON \
        -DGPU_RT_TYPE=OCL \
        -DENABLE_ONEDNN_FOR_GPU=ON && \
    cmake --build /openvino/build --target openvino_intel_gpu_plugin --parallel ${BUILD_JOBS:-$(nproc)} && \
    cp /openvino/bin/intel64/Release/libopenvino_intel_gpu_plugin.so /libopenvino_intel_gpu_plugin.so && \
    sha256sum /patches/*.patch > /patches.sha256

FROM ${BASE_IMAGE}

# Must match OPENVINO_TAG above: the plugin links against this release's
# libopenvino, which the wheel provides.
ARG OPENVINO_VERSION="2026.4.1"
ARG OPENVINO_TOKENIZERS_VERSION="2026.4.1.0"

USER root

RUN pip install --no-cache-dir --no-deps \
        "openvino==${OPENVINO_VERSION}" \
        "openvino-tokenizers==${OPENVINO_TOKENIZERS_VERSION}"

COPY --from=gpu-plugin-builder /libopenvino_intel_gpu_plugin.so /tmp/libopenvino_intel_gpu_plugin.so
COPY --from=gpu-plugin-builder /patches.sha256 /opt/openvino-gpu-patch/patches.sha256

# Replace the wheel's GPU plugin, then fail the build if the patched plugin
# cannot be loaded by this OpenVINO runtime (for example a version mismatch).
RUN set -e; \
    libs="$(python -c 'import openvino, pathlib; print(pathlib.Path(openvino.__file__).parent / "libs")')"; \
    install -m 0644 /tmp/libopenvino_intel_gpu_plugin.so "$libs/libopenvino_intel_gpu_plugin.so"; \
    rm /tmp/libopenvino_intel_gpu_plugin.so; \
    sha256sum "$libs/libopenvino_intel_gpu_plugin.so" > /opt/openvino-gpu-patch/plugin.sha256; \
    python -c 'import openvino as ov; v = ov.Core().get_versions("GPU")["GPU"]; print("GPU plugin:", v.description, v.build_number)'

USER appuser
