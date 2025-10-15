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
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
ENV PATH="/root/.local/bin:$PATH"

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh



# Copy only the Poetry configuration files first to leverage Docker caching
COPY pyproject.toml poetry.lock /opt/

# Install dependencies using Poetry
RUN poetry config virtualenvs.create false && poetry install --no-root

# ---- Stage 2: Final slim image ----
FROM python:3.11-slim

ARG UID=1000
ARG GID=1000

RUN apt-get update && apt-get install -y \
    curl \
    libmagic-dev \
    libgl1 \
    libsm6 \
    libglib2.0-0 \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
    
# Create a non-root user
RUN groupadd -g ${GID} appuser && \
    useradd -m -s /bin/bash -u ${UID} -g ${GID} appuser

# Copy installed dependencies from python-base
COPY --from=python-base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-base /usr/local/bin /usr/local/bin


COPY . /opt

WORKDIR /opt

# Change the user of working directory to non-root user
RUN chown -R appuser:appuser /opt

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/opt
ENV MODELS_DIR=/opt/models

# Command to run the application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]