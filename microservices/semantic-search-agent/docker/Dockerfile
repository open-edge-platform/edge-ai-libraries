FROM python:3.11-slim

# Proxy arguments (pass these during build if needed)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# Port arguments (can be overridden at build time)
ARG API_PORT=8080
ARG METRICS_PORT=9090

# Set proxy environment variables
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    no_proxy=${no_proxy} \
    API_PORT=${API_PORT} \
    METRICS_PORT=${METRICS_PORT}

LABEL maintainer="Intel AI Team"
LABEL description="Semantic Comparison Service - AI-powered item matching"

# Set working directory
WORKDIR /app

# Install system dependencies - commented out to avoid network issues
# Most Python packages now have prebuilt wheels
# RUN apt-get update && apt-get install -y \
#     --no-install-recommends \
#     build-essential \
#     && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY config/ ./config/

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose ports (will use ENV values at runtime)
EXPOSE ${API_PORT} ${METRICS_PORT}

# Health check (using environment variable for port)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f\"http://localhost:{os.getenv('API_PORT', 8080)}/api/v1/health\")" || exit 1

# Run application (port from environment variable)
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT:-8080} --log-level info"
