FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    FILTER_FILE_PATH=/app/all.json \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

WORKDIR /app

# Install uv directly and sync the project dependencies.
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/
COPY pyproject.toml ./
COPY uv.lock ./
COPY README.md ./

COPY main.py .
COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "app-proxy-mcp"]
