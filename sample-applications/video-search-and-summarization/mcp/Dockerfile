FROM python:3.12-slim

WORKDIR /app

# Install uv directly and sync the project dependencies.
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/
COPY pyproject.toml ./
COPY uv.lock ./
COPY README.md ./

COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "mcp-app"]
