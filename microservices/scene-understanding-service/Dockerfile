# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install --no-cache-dir uv==0.9.22

# Copy service (rule_engine is bundled as rule_engine/ sub-package)
COPY . /app/

# Create virtual environment and install dependencies
RUN uv sync

# Install performance-tools for metrics logging
RUN uv pip install git+https://github.com/intel-retail/performance-tools.git@main#subdirectory=benchmark-scripts

# Create non-root user
RUN useradd -m -u 1000 lpuser && \
    chmod +x docker-entrypoint.sh && \
    chown -R lpuser:lpuser /app

USER lpuser

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:8082/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
