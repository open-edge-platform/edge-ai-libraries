# -------- Stage 1: Ubuntu 22.04 Sources --------
FROM intel/dlstreamer-pipeline-server:3.1.0-extended-ubuntu22 AS ubuntu22-builder
LABEL stage="ubuntu22"

USER root

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget ca-certificates gnupg2 software-properties-common

COPY ./thirdparty/third_party_deb_apk_deps_ubuntu22.txt /thirdparty/

RUN sed -Ei 's/^# deb-src /deb-src /' /etc/apt/sources.list && \
    apt-get update && \
    mkdir -p /sources/ubuntu22 && cd /sources/ubuntu22 && \
    for package in $(cat /thirdparty/third_party_deb_apk_deps_ubuntu22.txt | xargs -n1); do \
        grep -l GPL /usr/share/doc/${package}/copyright; \
        exit_status=$?; \
        if [ $exit_status -eq 0 ]; then \
            apt-get source -q --download-only $package;  \
        fi \
    done

# -------- Stage 2: Ubuntu 24.04 Sources --------
FROM intel/dlstreamer-pipeline-server:3.1.0-extended-ubuntu24 AS ubuntu24-builder
LABEL stage="ubuntu24"

USER root

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget ca-certificates gnupg2 software-properties-common

COPY ./thirdparty/third_party_deb_apk_deps_ubuntu24.txt /thirdparty/

RUN echo "deb-src http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb-src http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb-src http://archive.ubuntu.com/ubuntu noble-security main restricted universe multiverse" >> /etc/apt/sources.list && \
    apt-get update && \
    mkdir -p /sources/ubuntu24 && cd /sources/ubuntu24 && \
    for package in $(cat /thirdparty/third_party_deb_apk_deps_ubuntu24.txt  | xargs -n1); do \
        grep -l GPL /usr/share/doc/${package}/copyright; \
        exit_status=$?; \
        if [ $exit_status -eq 0 ]; then \
            apt-get source -q --download-only $package;  \
        fi \
    done

# -------- Stage 3: GitHub Source Cloning --------
FROM ubuntu:22.04 AS github-cloner

USER root

ENV DEBIAN_FRONTEND=noninteractive

ARG UBUNTU_COPYLEFT_DEPS=""
ARG PYTHON_COPYLEFT_DEPS="https://git.launchpad.net/launchpadlib \
                          https://github.com/GNOME/pygobject \
                          https://github.com/FreeOpcUa/opcua-asyncio \
                          https://github.com/Lucretiel/autocommand \
                          https://github.com/certifi/python-certifi \
                          https://git.launchpad.net/wadllib \
                          https://git.launchpad.net/ubuntu/+source/python-apt \
                          https://git.launchpad.net/lazr.restfulclient \
                          https://git.launchpad.net/lazr.uri"
ARG PYTHON_NO_REPO_SOURCE="https://files.pythonhosted.org/packages/32/12/0409b3992c9a023d1521d9352d4c41bb1d43684ccb82899e716103e2bd88/bubblewrap-1.2.0.zip"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget unzip ca-certificates

WORKDIR /github-sources

RUN mkdir -p Ubuntu_Deb && cd Ubuntu_Deb && \
    for f in `echo $UBUNTU_COPYLEFT_DEPS | xargs -n1`; do \
        git clone --depth=1 "$f" && cd "$(basename "$f")" && rm -rf .git && cd ..; \
    done

RUN mkdir -p Python && cd Python && \
    for f in `echo $PYTHON_COPYLEFT_DEPS | xargs -n1`; do \
        git clone --depth=1 "$f" && cd "$(basename "$f")" && rm -rf .git && cd ..; \
    done && \
    if [ ! -z "$PYTHON_NO_REPO_SOURCE" ]; then \
        wget "$PYTHON_NO_REPO_SOURCE"; \
    fi

# -------- Final Stage --------
FROM ubuntu:22.04 AS final

LABEL description="Final image containing all third-party sources from Ubuntu and GitHub for the dlstreamer-pipeline-server microservice"

USER root

# Create non-root user
RUN useradd -ms /bin/bash sourceuser

# Install tools and adjust permissions
RUN apt-get update && apt-get install -y tree && \
    mkdir -p /opt && chown -R sourceuser:sourceuser /opt

# Copy sources
COPY --from=ubuntu22-builder /sources/ubuntu22 /opt/sources/ubuntu22
COPY --from=ubuntu24-builder /sources/ubuntu24 /opt/sources/ubuntu24
COPY --from=github-cloner /github-sources /opt/github-sources

# Fix ownership post-copy
RUN chown -R sourceuser:sourceuser /opt

USER sourceuser

WORKDIR /opt
CMD ["tree"]

