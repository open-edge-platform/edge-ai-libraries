# ---- Stage 1: Build dependencies ----
FROM python:3.11-slim AS python-base

# Set the working directory in the container
WORKDIR /opt

# Install system dependencies required for Poetry and the application
RUN apt-get update && apt-get install -y \
    libgl1 \
    libsm6 \
    curl \
    git \
    build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
ENV PATH="/root/.local/bin:$PATH"

# Copy only the Poetry configuration files first to leverage Docker caching
COPY pyproject.toml poetry.lock /opt/

# Install dependencies using Poetry
RUN poetry config virtualenvs.create false && poetry install --no-root \
    && rm -rf ~/.cache

# ---- Stage 2: Final slim image ----
FROM python:3.11-slim

ARG UID=1001
ARG GID=1001
ENV PYTHONPATH=/opt
ENV MODELS_DIR=/opt/models

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    libmagic-dev \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean
    
# Create a non-root user
RUN groupadd -g ${GID} appuser && \
    useradd -m -s /bin/bash -u ${UID} -g ${GID} appuser

# Copy installed dependencies from python-base
COPY --from=python-base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-base /usr/local/bin /usr/local/bin


COPY src /opt/src
COPY scripts /opt/scripts
COPY pyproject.toml /opt/
COPY docs/user-guide/api-docs/openapi.yaml /opt/docs/user-guide/api-docs/openapi.yaml

WORKDIR /opt

COPY docker/entrypoint.sh /opt/entrypoint.sh


RUN chown -R appuser:appuser /opt && \
    chmod +x /opt/entrypoint.sh

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Use our entrypoint script
ENTRYPOINT ["/opt/entrypoint.sh"]