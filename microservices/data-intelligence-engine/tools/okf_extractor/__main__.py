# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run the standalone REST service (no engine/model-runtime dependencies)."""
from __future__ import annotations

import os

import uvicorn

from .service import app


def main() -> None:
    uvicorn.run(
        app, host=os.getenv("OKF_EXTRACTOR_HOST", "0.0.0.0"),
        port=int(os.getenv("OKF_EXTRACTOR_PORT", "8080")),
    )


if __name__ == "__main__":
    main()