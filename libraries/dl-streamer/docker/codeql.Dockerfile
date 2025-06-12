ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS dev-base-image

USER root

RUN apt-get update && apt-get install -y curl unzip git && rm -rf /var/lib/apt/lists/*

RUN curl -f -L -o /tmp/codeql.zip https://github.com/github/codeql-cli-binaries/releases/download/v2.21.4/codeql-linux64.zip \
    && unzip /tmp/codeql.zip -d /opt \
    && ln -s /opt/codeql/codeql /usr/local/bin/codeql \
    && rm /tmp/codeql.zip

ENV PATH="/usr/local/bin:$PATH"

WORKDIR /home/dlstreamer/dlstreamer

RUN git clone https://github.com/github/codeql.git codeql-repo

CMD ["/bin/bash"]
