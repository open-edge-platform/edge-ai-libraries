# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.13-slim AS base

ARG RETRIEVER_BACKEND=vdms

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY pyproject.toml README.md ./

RUN pip install --upgrade pip && \
    pip install poetry==2.3.3 && \
    poetry config virtualenvs.create false && \
        case "${RETRIEVER_BACKEND}" in \
            vdms|faiss|pgvector|milvus) ;; \
            *) echo "Unsupported RETRIEVER_BACKEND='${RETRIEVER_BACKEND}'" >&2; exit 1 ;; \
        esac && \
        poetry install --only "main,backend-${RETRIEVER_BACKEND}" --no-root --sync

COPY src ./src
COPY scripts ./scripts

RUN chmod +x /app/scripts/entrypoint.sh && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-k", "uvicorn.workers.UvicornWorker", "src.main:app", "--timeout", "300"]
