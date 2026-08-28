---
name: vss-build
description: Build (and optionally push) the VSS Docker images from source with `make build`, `make build-deps`, and `make push` - the application services, the dependency microservices, or both, with registry/tag, proxy, and copyleft controls. Use when the user says "build vss", "rebuild the images", "build from source", "build the dependencies", or "push the vss images". The Makefile is the source of truth for builds; there is no build.sh at the app root.
license: Apache-2.0
metadata:
  version: "2.0.0"
  tags: "vss build development"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Build

Build VSS container images with the **Makefile** - the source of truth for
builds in this repo. There is **no `build.sh`** at the app root; the only
`build.sh` scripts left are upstream ones inside `microservices/`, which
`make build-deps` calls for you. Run the commands yourself and relay output.

The canonical human-readable guide is
[`docs/user-guide/build-from-source.md`](../../../docs/user-guide/build-from-source.md);
keep answers consistent with it and with the Makefile itself.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It first tries to find an existing VSS checkout -
walking up from the current directory and inspecting the enclosing git repo - and
reuses it **without ever re-cloning**. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/video-search-and-summarization` from `main`. It prints the
resolved app root on stdout:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-build. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-build"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT` (the
Makefile lives there). To pull from a fork/branch or reuse a specific checkout
dir, override `VSS_REPO_URL`, `VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before
running it.

## What the build targets do

| Command | Builds |
|---|---|
| `make build` | Application services: `pipeline-manager`, `vss-ui`, `video-search` (from `search-ms/`), `video-ingestion` |
| `make build-deps` | Dependency microservices: `multimodal-dataprep`, `multimodal-embedding-serving`, and `vector-retriever-vdms` + `vector-retriever-milvus` (one image per backend) |
| `make push` | Push every app **and** dependency image to the configured registry |
| `make list` | Print the resolved tag, registry prefix, and the exact image names - use it to confirm config before building |
| `make clean` | Remove the locally built **application** images (not the dependency ones) |
| `make help` | All targets, including test/scan/deploy |

Run `make build-deps` the first time, or when those upstream microservices
changed; otherwise plain `make build` is enough for day-to-day app changes.
Order between the two does not matter - they are independent.

The `make deploy-*` targets already declare `build build-deps` as prerequisites,
so a deploy through [`vss-deploy`](../vss-deploy/SKILL.md)'s Makefile path
rebuilds first; a separate build is only needed when you want images without
deploying.

## Controls (registry, tag, proxy, copyleft)

| Var | Effect | Default |
|---|---|---|
| `REGISTRY_URL` | registry host prefix (one trailing `/` normalised) | `.env` value, shipped as `intel/` |
| `PROJECT_NAME` | project/namespace segment after the registry | `.env` value, shipped empty |
| `REGISTRY` | the whole prefix at once; overrides the two above | `$(REGISTRY_URL)$(PROJECT_NAME)` |
| `TAG` | image tag | `.env` value, else `latest` |
| `http_proxy` / `https_proxy` / `no_proxy` | passed through as Docker `--build-arg`s; omitted entirely when unset | inherited |
| `ADD_COPYLEFT_SOURCES=true` | builds with `--build-arg COPYLEFT_SOURCES=true` | unset |

Every image is named `<REGISTRY_URL><PROJECT_NAME>/<service>:<TAG>`.

**Where the values come from, highest precedence first:**

1. `make build TAG=dev REGISTRY_URL=...` - command-line variables win over everything.
2. Exported shell variables (`export TAG=dev`).
3. `.env` at the app root, which the Makefile reads at parse time. It is
   **auto-created from `.env.example`** on the first `make build` / `build-deps` /
   `push`, so with no overrides you get the shipped `intel/` prefix - **not**
   bare local names.

To build genuinely un-prefixed local images, clear the prefix explicitly:

```bash
make build REGISTRY_URL= PROJECT_NAME=      # → pipeline-manager:latest, …
```

Build and deploy must agree: `setup.sh` composes `REGISTRY` from
`REGISTRY_URL`/`PROJECT_NAME` the same way, so Compose only finds your images if
the prefix and `TAG` match what you built. See
[`vss-deploy/vss.config`](../vss-deploy/vss.config) (`REGISTRY_URL`, `TAG`) and keep
the two in sync.

## `make build-deps` needs the sibling `microservices/` tree

`build-deps` reaches out to `../../microservices` for the dataprep,
embedding-serving, and vector-retriever sources, and fails fast if they are
missing. A bootstrap clone is **sparse** - it contains only
`sample-applications/video-search-and-summarization` - so widen it before
building dependencies:

```bash
[ -d ../../microservices ] || \
  git -C "$(git rev-parse --show-toplevel)" sparse-checkout add microservices
```

No-op in a full clone (the directory is already there). `make build` alone does
not need this.

## Typical flows

```bash
# Local app rebuild, then deploy:
make build
#   ! export VSS_CREDENTIALS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/vss/vss.credentials" && ./.github/skills/vss-deploy/scripts/gen-secrets.sh && source .github/skills/vss-deploy/vss.config && source "$VSS_CREDENTIALS_FILE" && source setup.sh --summary

# First-time / dependency refresh:
make build-deps && make build

# Build for a registry and push:
make build build-deps push REGISTRY_URL=registry.example.com PROJECT_NAME=vss-team TAG=v0.9.2

# Compliance build with copyleft sources, no push:
make build-deps build ADD_COPYLEFT_SOURCES=true TAG=compliance-2026-07
```

## Prerequisites & gotchas

- **Docker** and **make** required. Poetry is *not* needed on the host - the
  embedding-serving image installs it inside the build.
- `make push` **refuses to run with an empty prefix** rather than pushing
  un-namespaced images to docker.io; set `REGISTRY_URL`(+`PROJECT_NAME`) or
  `REGISTRY`. It skips images that are not present locally, so build first.
- Behind a corporate proxy, export `http_proxy`/`https_proxy`/`no_proxy` before
  building so they reach the image builds as build args.
- `make clean` only removes the four application images; dependency images stay.
- After building locally, deploy with [`vss-deploy`](../vss-deploy/SKILL.md); `setup.sh`
  uses the images you just built (match `TAG`/`REGISTRY_URL`).

## Verify

```bash
make list      # expected image names for the current config
docker images | grep -E 'pipeline-manager|vss-ui|video-search|video-ingestion|multimodal-|vector-retriever'
```
