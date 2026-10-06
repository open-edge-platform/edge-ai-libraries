# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM golang:1.25-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git build-base linux-headers

WORKDIR /build

# Clone specific tag and build
ARG TAG=gpu-v0.10.1
RUN git clone --depth 1 --branch ${TAG} \
    https://github.com/intel/intel-resource-drivers-for-kubernetes.git repo

WORKDIR /build/repo

# Sync vendor and build static binary (CGO_ENABLED=0 avoids musl dynamic link)
RUN go mod vendor && \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -a -ldflags "-s -w" \
    -mod vendor -o /intel-cdi-specs-generator-gpu ./cmd/cdi-specs-generator

# Minimal runtime stage for extraction
FROM scratch
COPY --from=builder /intel-cdi-specs-generator-gpu /intel-cdi-specs-generator-gpu
# scratch has no shell; HEALTHCHECK NONE is explicit for minimal binary-only images
HEALTHCHECK NONE
ENTRYPOINT ["/intel-cdi-specs-generator-gpu"]
