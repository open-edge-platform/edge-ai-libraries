# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -u 1001 appuser

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-group test --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

COPY src/ ./src/

# Third-party notices for the Python packages installed above
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
        pip list --format=freeze | cut -d= -f1 | while read -r pkg; do \
            meta=$(pip show "$pkg" 2>/dev/null); \
            lic=$(echo "$meta" | grep -i '^License:' | grep -E 'MPL|GPL|General Public License|EPL|Eclipse Public License|CDDL|LGPL'); \
            if [ -n "$lic" ]; then \
                echo "Downloading source for $pkg with license: $lic"; \
                pip download --no-cache-dir --no-binary :all: --no-deps "$pkg" || true; \
            fi; \
        done; \
        rm -rf /var/lib/apt/lists/*; \
    fi

RUN mkdir -p /app/output && chown -R appuser:appuser /app/output

USER appuser

EXPOSE 5002

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "5002", "--workers", "1"]
