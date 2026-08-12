# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.13-slim

ARG INSTALL_COMPRESSOR=false

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
COPY vendor/adaptive-token-compressor/ /libs/adaptive-token-compressor/

RUN if [ "$INSTALL_COMPRESSOR" = "true" ]; then \
      pip install --no-cache-dir ".[ov]" && \
      pip install --no-cache-dir "/libs/adaptive-token-compressor"; \
    else \
      pip install --no-cache-dir ".[ov]"; \
    fi

RUN pip install --no-cache-dir --upgrade "transformers>=5.2"

COPY scripts/install_gpu_runtime.sh /tmp/install_gpu_runtime.sh
RUN bash /tmp/install_gpu_runtime.sh && rm /tmp/install_gpu_runtime.sh

# Create non-root user and hand over /app
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
