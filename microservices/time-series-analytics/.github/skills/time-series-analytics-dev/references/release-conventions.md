<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Release & Versioning Conventions

## `CHANGELOG.md`

Entries are grouped by version heading (`## [2026.1] - June 2026`) with
`### Added` / `### Changed` / `### Fixed` / `### Documentation` subsections.
Each line ends with a PR reference in the form `([#2087])` — add the
matching link-reference definition at the bottom of the file (or wherever
existing `[#NNNN]` definitions live) rather than an inline URL. Pick the
subsection by what actually changed, not by where it's convenient: a
behavior change to an existing feature is `Changed`, a new endpoint or
capability is `Added`, a regression fix is `Fixed`.

## Where the version number itself lives

A version bump touches multiple files that must stay in sync — this is the
one place in this service where a single "release" edit has to fan out
across the repo:

| File | Field |
|---|---|
| `docker/.env` | `IMAGE_SUFFIX` (e.g. `"2026.2.0"`), `WEEKLY_BUILD_DATE` for dated dev builds |
| `helm/values.yaml` | `images.image_suffix`, `images.weekly_build_date` |
| `README-dockerhub.md` | New version section with Docker Compose + Helm deployment doc links (see existing entries for the exact format) |
| `CHANGELOG.md` | New `## [YYYY.M]` heading |

Docker Hub image tags and the Helm chart's `image_suffix` are expected to
match for a given release — check both when bumping, not just one.

## `Dockerfile` build args worth knowing before touching the image

| Arg | Current pin | Notes |
|---|---|---|
| `KAPACITOR_VERSION` | 1.8.6 | Sparse git checkout of `influxdata/kapacitor` for the UDF agent lib; also the `.deb` version installed for the daemon — bump both together or they'll mismatch |
| `PYTHON_VERSION` | 3.13 | Base image tag (`python:${PYTHON_VERSION}-slim`) |
| `INSTALL_DRIVER_VERSION` | pinned in `scripts/install_gpu_drivers.sh` invocation | Intel GPU driver version |

## Dependency/security bumps

`requirements.txt` (runtime) and `tests/requirements.txt` /
`tests-functional/requirements.txt` (test-only) are pinned with `==`.
`third-party-programs.txt` and `.trivyignore` need review whenever
dependencies change — see recent `CHANGELOG.md` "Fixed" entries for the
pattern (e.g. bumping `python-multipart`/`pytest*` for CVEs, suppressing
unfixable upstream Kapacitor CVEs in `.trivyignore` with a comment
explaining why each suppression is safe).

## Documentation

User-facing docs live under
[`docs/user-guide/`](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/time-series-analytics/docs/user-guide);
[`release-notes.md`](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/time-series-analytics/docs/user-guide/release-notes.md)
and the `release-notes/` folder there hold the published release notes
(separate from `CHANGELOG.md`, which is the repo-internal running log).
Keep both in sync for a real release — `CHANGELOG.md` is the engineering
record, release notes are the user-facing summary.
