# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Application build identifiers for ViPPET.

Resolves the release/build identifiers exposed via ``GET /status`` and the
FastAPI OpenAPI document:

- ``VIPPET_VERSION`` - release string / image tag (e.g. "2026.2.0-rc2").
- ``VIPPET_REVISION`` - git commit hash of the source tree the image was
  built from, suffixed with "-dirty" if the working tree had uncommitted
  changes at build time (e.g. "a1b2c3d" or "a1b2c3d-dirty").
"""

import os

# Injected at build time from DOCKER_TAG (see Dockerfile / compose.yml).
VIPPET_VERSION: str = os.environ.get("VIPPET_VERSION", "").strip() or "unknown"

# Injected at build time from the git commit hash (see setup_env.sh).
VIPPET_REVISION: str = os.environ.get("VIPPET_REVISION", "").strip() or "unknown"
