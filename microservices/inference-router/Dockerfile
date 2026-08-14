# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---- Fetch stage: vendor the adaptive-token-compressor source ----
# The library lives inside a larger monorepo; fetch only its subdirectory via a
# sparse, blobless clone so `docker build` is self-contained (no build script).
FROM python:3.13-slim AS compressor-src

ARG COMPRESSOR_REPO=https://github.com/open-edge-platform/edge-ai-libraries.git
ARG COMPRESSOR_REF=release-2026.2.0
ARG COMPRESSOR_SUBDIR=libraries/adaptive-token-compressor

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${COMPRESSOR_REF}" --filter=blob:none --sparse \
      "${COMPRESSOR_REPO}" /tmp/edge-ai-libraries \
    && git -C /tmp/edge-ai-libraries sparse-checkout set --no-cone "${COMPRESSOR_SUBDIR}" \
    && if [ ! -d "/tmp/edge-ai-libraries/${COMPRESSOR_SUBDIR}" ]; then \
         echo "Error: ${COMPRESSOR_SUBDIR} not found in ${COMPRESSOR_REPO}" >&2; exit 1; \
       fi \
    && mkdir -p /libs \
    && cp -r "/tmp/edge-ai-libraries/${COMPRESSOR_SUBDIR}" /libs/adaptive-token-compressor \
    && rm -rf /tmp/edge-ai-libraries

# ---- Runtime stage ----
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
COPY --from=compressor-src /libs/adaptive-token-compressor/ /libs/adaptive-token-compressor/

RUN pip install --no-cache-dir ".[ov]" && \
    pip install --no-cache-dir "/libs/adaptive-token-compressor"

RUN pip install --no-cache-dir --upgrade "transformers>=5.2"

COPY scripts/install_gpu_runtime.sh /tmp/install_gpu_runtime.sh
RUN bash /tmp/install_gpu_runtime.sh && rm /tmp/install_gpu_runtime.sh

# Create non-root user and hand over /app
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
