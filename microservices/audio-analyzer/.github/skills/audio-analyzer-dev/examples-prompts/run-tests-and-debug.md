<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Run the right test suite and diagnose a failing Audio Analyzer deployment:
- Identify whether a request calls for the root-level lightweight tests (`tests/*.py`) or the tiered functional suite (`tests/functional/`), and use the correct invocation for each
- Run the tier1 functional tests without requiring model weights, Docker, or GPU
- Run the Tier-3 Docker build verification suite to validate a Dockerfile/Compose change without a full deployment
- Use `GET /v1/model-info` and `GET /v1/performance` to confirm the active model/device and the last call's latency on a running service

If a container exits right after startup, grep its logs for the "ASR model is unavailable" warning and explain what it means before investigating further.
