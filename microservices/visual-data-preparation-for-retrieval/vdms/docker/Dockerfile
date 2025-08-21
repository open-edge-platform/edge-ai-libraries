# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG ARCH="cpu"
FROM python:3.13-slim AS python-base
ARG ARCH
# Setting env vars for python, pip and poetry
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \ 
    # off value above actually emplies, no cache will be used. Confusing.
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.8.5 \
    # Poetry installation location
    POETRY_HOME="/opt/poetry" \
    # Create the virtual environment dir .venv in the project's root
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    # Disable interactive prompts
    POETRY_NO_INTERACTION=1 \
    # Location where packages gets installed
    SETUP_PATH="/opt/projsetup" \
    # Location where virtual env is created
    VENV_PATH="/opt/projsetup/.venv"

# Add poetry and venv to path
ENV PATH="$PATH:$POETRY_HOME/bin:$VENV_PATH/bin"

# upgrade pip to the latest version
RUN pip install --upgrade pip

# `builder-base` image used to install build dependecies and required packages 
FROM python-base AS builder-base
ARG ARCH
RUN apt-get update && apt-get install --no-install-recommends --fix-missing -y \
    curl \
    build-essential

# Install poetry. Installs in $POETRY_HOME with version $POETRY_VERSION
RUN curl -sSL https://install.python-poetry.org | python3 - 

WORKDIR $SETUP_PATH
COPY poetry.lock pyproject.toml ./

# Run poetry lock to install build dependencies
RUN poetry lock --no-update

# Install runtime (prod) deps. Uses $POETRY_VIRTUALENVS_IN_PROJECT to create venv.
# If value of ARCH is cpu, install with optional cpu dependencies else install main dependencies
RUN if [ ${ARCH} = "cpu" ]; \
    then poetry install --with cpu; \
    else poetry install --only main; fi


# `dev` image is used during development / testing
FROM python-base AS dev
ENV FASTAPI_ENV=development
WORKDIR $SETUP_PATH

# Copy the poetry installation and the virtual env to current image
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

# Install dev dependencies. Prod dependencies are already installed.
RUN poetry install --with dev

# Copy the entrypoint script and makeit executable
COPY ./scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Source code will be mounted here
WORKDIR /app
RUN mkdir -p /tmp/dataprep/videos
EXPOSE 8000

ENTRYPOINT [ "/entrypoint.sh" ] 
CMD [ "poetry", "run", "uvicorn", "--host", "0.0.0.0", "--port", "8000", "--reload", "src.app:app" ]

# Linter stage to lint code in dev image
FROM dev AS lint
COPY . .
RUN black --config ./pyproject.toml --check tests src
RUN isort --settings-path ./pyproject.toml --check-only .

# Final dev stage after passing linting and tests criteria.
FROM lint AS final-dev
ARG COVERAGE_REQ
RUN coverage run --rcfile ./pyproject.toml -m pytest ./tests
RUN coverage report -m --fail-under $COVERAGE_REQ

# Generate test coverage report on lint stage and serve it using python http server.
FROM lint AS report
COPY ./scripts/reporter.sh /reporter.sh
RUN chmod +x /reporter.sh
CMD [ "/reporter.sh" ]

# `prod` image used for runtime
FROM python-base AS prod
ENV FASTAPI_ENV=production

COPY --from=builder-base $SETUP_PATH $SETUP_PATH

COPY ./scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY . /app/

# Optionally download copyleft sources if requested
ARG COPYLEFT_SOURCES=false
RUN if [ "$COPYLEFT_SOURCES" = "true" ]; then \
        apt-get update && \
        # Get list of installed deb packages with copyleft licenses \
        sed -Ei 's/# deb-src /deb-src /' /etc/apt/sources.list && \
        apt-get update && \
        mkdir -p /copyleft_sources/deb && cd /copyleft_sources/deb && \
        echo -n $null > copyleft_package_list.txt && \
        for package in $(dpkg -l | awk '/^ii/ {print $2}' | cut -d: -f1); do \
            grep -l 'Copyleft\|GPL\|LGPL\|EPL\|MPL\|CDDL' /usr/share/doc/${package}/copyright; \
            exit_status=$?; \
            if [ $exit_status -eq 0 ]; then \
                echo $package >> copyleft_package_list.txt; \
                apt-get source -q --download-only $package; \
            fi; \
        done; \
        # Get source code for installed Python packages with copyleft licenses \
        mkdir -p /copyleft_sources/python && \
        cd /copyleft_sources/python && \
        apt-get update && apt-get install -y gcc build-essential libffi-dev python3-dev && \
        # Download python package sources with relevant licenses \
        pip3 freeze | cut -d= -f1 | while read pkg; do \
            meta=$(pip3 show $pkg 2>/dev/null); \
            lic=$(echo "$meta" | grep -i '^License:' | grep -E 'MPL|GPL|General Public License|EPL|Eclipse Public License|CDDL|LGPL'); \
            if [ ! -z "$lic" ]; then \
                echo "Downloading source for $pkg with license: $lic"; \
                pip3 download --no-binary :all: $pkg || true; \
            fi; \
        done; \
        apt-get remove --purge -y gcc build-essential libffi-dev python3-dev; \
    fi
    
WORKDIR /app
RUN mkdir -p /tmp/dataprep/videos
EXPOSE 8000

ENTRYPOINT [ "/entrypoint.sh" ]
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-k", "uvicorn.workers.UvicornWorker", "src.app:app", "--timeout", "300", "--access-logfile", "-"]
