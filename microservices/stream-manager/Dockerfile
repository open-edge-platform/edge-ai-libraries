# SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM golang:1.26-bookworm AS build

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/api-server ./cmd/api-server

FROM debian:bookworm-slim

RUN apt-get update \
	&& apt-get install -y --no-install-recommends ca-certificates ffmpeg \
	&& rm -rf /var/lib/apt/lists/* \
	&& groupadd --system --gid 10001 stream-manager \
	&& useradd --system --uid 10001 --gid stream-manager --home-dir /nonexistent --shell /usr/sbin/nologin stream-manager \
	&& install -d --owner=10001 --group=10001 /var/lib/stream-manager

COPY --from=build --chown=10001:10001 /out/api-server /usr/local/bin/api-server

USER 10001:10001
EXPOSE 18080
ENTRYPOINT ["/usr/local/bin/api-server"]
