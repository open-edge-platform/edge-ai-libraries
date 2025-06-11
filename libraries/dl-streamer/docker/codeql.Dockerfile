ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS dev-base-image
RUN apt-get update && apt-get install -y curl unzip && rm -rf /var/lib/apt/lists/*
RUN curl -L -o codeql.zip https://github.com/github/codeql-cli-binaries/releases/download/codeql-cli-2.11.10/codeql-linux64.zip && \
    unzip codeql.zip -d /usr/local/bin && \
    rm codeql.zip
ENV PATH="/usr/local/bin/codeql:$PATH"
WORKDIR /src
CMD ["/bin/bash"]
