---
name: vss-build
description: Build (and optionally push) the VSS Docker images from source using build.sh — the application services, the pre-built dependency services, or both, with registry/tag and proxy controls. Use when the user says "build vss", "rebuild the images", "build from source", "build the dependencies", or "push the vss images". build.sh is the source of truth for builds, not the Makefile.
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "vss build development"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Build

Build VSS container images with **`build.sh`** — the true source for builds in
this repo. Do **not** drive builds via the Makefile here. Run the commands
yourself and relay output.

## What build.sh does

| Command | Builds |
|---|---|
| `./build.sh` | Application services: `video-ingestion`, `pipeline-manager`, `search-ms`, UI |
| `./build.sh --dependencies` | Dependency services: `vdms-dataprep`, `multimodal-embedding-serving` (needs **poetry** for the embedding wheel) |
| `./build.sh --push` | Push all built images to the configured registry |
| `./build.sh --help` | Usage |

Run `--dependencies` before the plain build the first time, or when those
upstream services changed; otherwise the plain `./build.sh` is enough for
day-to-day app changes.

## Controls (env vars)

`build.sh` reads these from the shell (it does not read a `.env`):

| Var | Effect | Default |
|---|---|---|
| `REGISTRY_URL` | registry host prefix (trailing `/` auto-added) | empty (local tags) |
| `PROJECT_NAME` | project/namespace segment after the registry | empty |
| `TAG` | image tag | `latest` |
| `http_proxy` / `https_proxy` / `no_proxy` | passed through as Docker `--build-arg`s | inherited |
| `COPYLEFT_SOURCES` | if set, builds with `--build-arg COPYLEFT_SOURCES=true` | unset |

With no `REGISTRY_URL` you get local image names (fine for local deploy via
`setup.sh`). Final image prefix is `${REGISTRY_URL}/${PROJECT_NAME}/`.

Reuse the same values you deploy with — see
[`vss-up/vss.config.env`](../vss-up/vss.config.env) (`REGISTRY_URL`, `TAG`).

## Typical flows

```bash
# Local app rebuild (no registry), then deploy:
./build.sh
#   ! ./.github/skills/vss-up/scripts/gen-secrets.sh && source .github/skills/vss-up/vss.config.env && source .github/skills/vss-up/vss.secrets.env && source setup.sh --summary

# First-time / dependency refresh:
./build.sh --dependencies && ./build.sh

# Build for a registry and push:
export REGISTRY_URL=intel TAG=dev
./build.sh && ./build.sh --push
```

## Prerequisites & gotchas

- **Docker** required for any build; **poetry** also required for
  `--dependencies` (builds the multimodal-embedding wheel) — build.sh aborts
  early with an install hint if missing.
- Behind a corporate proxy, export `http_proxy`/`https_proxy`/`no_proxy` before
  building so they reach the image builds.
- After building locally, deploy with [`vss-up`](../vss-up/SKILL.md); `setup.sh`
  uses the images you just built (match `TAG`/`REGISTRY_URL`).

## Verify

```bash
docker images | grep -E 'pipeline-manager|search|video-ingestion|vss|embedding|dataprep'
```
