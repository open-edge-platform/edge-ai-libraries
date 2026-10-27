# SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM golang:1.26 AS builder-base

COPY --from=mwader/static-ffmpeg:9.0.2 /ffmpeg /usr/local/bin/ffmpeg
COPY --from=mwader/static-ffmpeg:9.0.2 /ffprobe /usr/local/bin/ffprobe
COPY --from=mwader/static-ffmpeg:9.0.2 /versions.json /licenses/ffmpeg/versions.json
RUN ffmpeg -L > /licenses/ffmpeg/ffmpeg_license.txt && \
    ffprobe -L > /licenses/ffmpeg/ffprobe_license.txt && \
    ffmpeg -version > /licenses/ffmpeg/ffmpeg_version.txt && \
    ffprobe -version > /licenses/ffmpeg/ffprobe_version.txt && \
    cp /usr/share/common-licenses/GPL-3 /licenses/ffmpeg/COPYING.GPLv3 && \
    sha256sum /usr/local/bin/ffmpeg /usr/local/bin/ffprobe > /licenses/ffmpeg/SHA256SUMS

RUN printf '%s\n' 'This software is based in part on the work of the Independent JPEG Group.' > /licenses/ffmpeg/NOTICE

FROM builder-base AS go-builder
WORKDIR /app

ARG VERSION=NA
ARG BUILD_NUMBER=NA
ARG BUILD_DATE=$(date '+%Y-%m-%dT%H:%M:%S%z')

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="\
        -s \
        -w \
        -extldflags '-z relro -z now' \
        -X main.Version=${VERSION} \
        -X main.BuildDate=${BUILD_DATE} \
        -X main.BuildNumber=${BUILD_NUMBER}" \
    -o stream-manager ./cmd/api-server

RUN mkdir -m 0700 /data && chown 65532:65532 /data

FROM gcr.io/distroless/static-debian13:nonroot
WORKDIR /

ENV SM_DATA_DIR=/data
ENV SM_HTTP_ADDR=:8080

COPY --from=builder-base /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder-base /usr/local/bin/ffprobe /usr/local/bin/ffprobe
COPY --from=builder-base /licenses/ /usr/share/licenses/
COPY --from=go-builder /app/stream-manager /stream-manager

COPY --from=go-builder --chown=nonroot:nonroot --chmod=0700 /data /data

EXPOSE 8080

USER nonroot:nonroot

ENTRYPOINT ["/stream-manager"]
