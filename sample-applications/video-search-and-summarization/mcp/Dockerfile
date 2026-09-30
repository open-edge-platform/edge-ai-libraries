FROM python:3.12-slim AS python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=2.4.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    # Keep pip/setuptools out of the runtime venv: they are only needed at
    # build time, and pip vendors an SBOM that reports vulnerable versions of
    # packages it does not actually ship as importable code.
    POETRY_VIRTUALENVS_OPTIONS_NO_PIP=true \
    POETRY_VIRTUALENVS_OPTIONS_NO_SETUPTOOLS=true \
    SETUP_PATH="/opt/projsetup" \
    VENV_PATH="/opt/projsetup/.venv"

# Add poetry and venv to path
ENV PATH="$PATH:$POETRY_HOME/bin:$VENV_PATH/bin"

FROM python-base AS builder-base

RUN apt-get update && apt-get install --no-install-recommends -y curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python -

WORKDIR $SETUP_PATH
COPY pyproject.toml poetry.lock README.md ./
COPY src ./src

RUN poetry install --only main --no-interaction --no-ansi

FROM python-base AS prod

COPY --from=builder-base $SETUP_PATH $SETUP_PATH

WORKDIR $SETUP_PATH

RUN addgroup --system app \
    && adduser --system --ingroup app --home $SETUP_PATH app \
    && chown -R app:app $SETUP_PATH

USER app

EXPOSE 8000

CMD ["mcp-app"]
