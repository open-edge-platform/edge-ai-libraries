# ---- Stage 1: Build dependencies ----
FROM python:3.11-slim AS python-base

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for Poetry and the application
RUN apt-get update && apt-get install -y \
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
COPY pyproject.toml poetry.lock /app/

# Install dependencies using Poetry
RUN poetry config virtualenvs.create false && poetry install --no-root

# ---- Stage 2: Final slim image ----
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed dependencies from python-base
COPY --from=python-base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-base /usr/local/bin /usr/local/bin

# Copy the application files into the container
COPY . /app

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "--host", "0.0.0.0", "app.main:app"]