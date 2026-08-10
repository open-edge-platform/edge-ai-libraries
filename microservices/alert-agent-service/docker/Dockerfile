# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---------------------------------------------------------------------------
# Stage 1 — dependency installer
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml ./
COPY uv.lock ./
RUN uv sync --no-dev --no-install-project 

# ---------------------------------------------------------------------------
# Stage 2 — lean runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SNAPSHOT_DIR=/app/snapshots

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser resources/tools.json ./resources/tools.json

COPY third_party_programs.txt /licenses/third_party_programs.txt

# Optionally fetch source for any copyleft-licensed dependency (deb or pip) so
# it can be redistributed alongside the image for license compliance. Off by
# default; set --build-arg COPYLEFT_SOURCES=true to enable.
ARG COPYLEFT_SOURCES=false
RUN if [ "$COPYLEFT_SOURCES" = "true" ]; then \
        set -e; \
        sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
        apt-get update && \
        mkdir -p /copyleft_sources/deb && cd /copyleft_sources/deb && \
        : > copyleft_package_list.txt && \
        for package in $(dpkg -l | awk '/^ii/ {print $2}' | cut -d: -f1); do \
            if [ -f "/usr/share/doc/${package}/copyright" ] && \
               grep -lqE 'Copyleft|GPL|LGPL|EPL|MPL|CDDL' "/usr/share/doc/${package}/copyright"; then \
                echo "${package}" >> copyleft_package_list.txt; \
                apt-get source -q --download-only "${package}" || true; \
            fi; \
        done; \
        mkdir -p /copyleft_sources/python && cd /copyleft_sources/python && \
        python -m ensurepip --default-pip 2>/dev/null || true; \
        python -c "import importlib.metadata,re;[print(d.metadata['Name']) for d in importlib.metadata.distributions() if re.search(r'MPL|GPL|General Public License|EPL|Eclipse Public License|CDDL|LGPL',(d.metadata.get('License-Expression') or d.metadata.get('License') or '')+' '.join(c for c in (d.metadata.get_all('Classifier') or []) if 'License' in c))]" > /tmp/copyleft_pkgs.txt; \
        while read -r pkg; do \
            echo "Downloading source for copyleft package: $pkg"; \
            python -m pip download --no-cache-dir --no-binary :all: --no-deps "$pkg" || true; \
        done < /tmp/copyleft_pkgs.txt; \
        rm -rf /var/lib/apt/lists/*; \
    fi

RUN mkdir -p /app/snapshots /app/resources \
    && chown -R appuser:appuser /app/snapshots /app/resources

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/v1/health || exit 1

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port 8000"]
