FROM ubuntu:22.04
LABEL description="This Dockerfile is used to download the source code of third-party dependencies for the dlstreamer-pipeline-server microservice."

USER root

# Install git and wget
RUN apt-get update && \
    apt-get install -y git wget

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

COPY ./thirdparty/third_party_deb_apk_deps.txt /thirdparty/
COPY ./thirdparty/third_party_programs.txt /thirdparty/

RUN sed -Ei 's/# deb-src /deb-src /' /etc/apt/sources.list && \
    apt-get update && \
    root_dir=$PWD && \
    mkdir -p ./apt-sources/dlstreamer-pipeline-server && cd ./apt-sources/dlstreamer-pipeline-server && \
    cp /thirdparty/third_party_deb_apk_deps.txt . && \
    for line in $(cat third_party_deb_apk_deps.txt | xargs -n1); \
        do \
        package=$(echo $line); \
        grep -l GPL /usr/share/doc/${package}/copyright; \
        exit_status=$?; \
        if [ $exit_status -eq 0 ]; then \
            apt-get source -q --download-only $package;  \
        fi \
        done && \
    cd $root_dir && \
    echo "Cloning Debian and Ubuntu github deps..." && \
    mkdir -p ./github-sources/Ubuntu_Deb && cd ./github-sources/Ubuntu_Deb && \
    for f in `echo $UBUNTU_COPYLEFT_DEPS | xargs -n1`; do git clone $f && \
    cd "$(basename "$f")" && \
    rm -rf .git && \
    cd ..; done && \
    cd ../ && \
    mkdir -p Python && cd Python && \
    echo "Cloning Python github dependency" && \
    for f in `echo $PYTHON_COPYLEFT_DEPS | xargs -n1`; do git clone $f && \
    wget $PYTHON_NO_REPO_SOURCE && \
    cd "$(basename "$f")" && \
    rm -rf .git && \
    cd ..; done && \
    cd $root_dir && \
    echo "Download source for $(ls | wc -l) third-party packages: $(du -sh)"; \
    rm -rf /var/lib/apt/lists/*;\