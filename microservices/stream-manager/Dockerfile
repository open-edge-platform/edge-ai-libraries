# SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM golang:1.26 AS go-builder
WORKDIR /app

ARG VERSION=0.0.1
ARG BUILD_NUMBER=NA
ARG BUILD_DATE=$(date '+%Y-%m-%dT%H:%M:%S%z')

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build \
    -ldflags="\
        -s \
        -w \
        -X main.Version=${VERSION} \
        -X main.BuildDate=${BUILD_DATE} \
        -X main.BuildNumber=${BUILD_NUMBER}" \
    -o stream-manager ./cmd/api-server

RUN mkdir -m 0700 /data && chown 65532:65532 /data

FROM gcr.io/distroless/static-debian13:nonroot
WORKDIR /

ENV SM_DATA_DIR=/data
ENV SM_HTTP_ADDR=:8080

COPY --from=mwader/static-ffmpeg:9.0.2 /ffmpeg /usr/local/bin/ffmpeg
COPY --from=mwader/static-ffmpeg:9.0.2 /ffprobe /usr/local/bin/ffprobe
COPY --from=go-builder /app/stream-manager /stream-manager

COPY --from=go-builder --chown=nonroot:nonroot --chmod=0700 /data /data

EXPOSE 8080

USER nonroot:nonroot

ENTRYPOINT ["/stream-manager"]
