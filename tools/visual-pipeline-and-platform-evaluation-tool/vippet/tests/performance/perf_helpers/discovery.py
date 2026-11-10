# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fetch the live ViPPET inventory and build the benchmark matrix.

Only read-only ``GET`` endpoints are used (``/pipelines``, ``/devices``,
``/models``), so this is safe to call from ``--dry-run``.

Requires the functional-test ``helpers`` package on ``sys.path`` and
``VIPPET_BASE_URL`` set *before* first import, because
``helpers.config.BASE_URL`` is read once at import time.
"""

import requests

from helpers.api_helpers import fetch_devices, fetch_pipelines
from helpers.pipeline_case_helpers import missing_models_per_pipeline

from .matrix import Matrix, MatrixFilters, build_matrix


def discover_matrix(filters: MatrixFilters) -> Matrix:
    """Query ViPPET and classify every (pipeline, variant). Raises on I/O errors."""
    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})
        pipelines = fetch_pipelines(session)
        devices = fetch_devices(session)
        missing = missing_models_per_pipeline(session)
    return build_matrix(pipelines, devices, missing, filters)
