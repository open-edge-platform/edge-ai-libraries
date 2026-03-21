# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi.testclient import TestClient

from video_analyzer.core.settings import settings


@pytest.mark.api
def test_health_endpoint(test_client: TestClient):
    """Test the health check API endpoint"""

    response = test_client.get("/v1/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == settings.API_STATUS
    assert data["version"] == settings.API_VER
    assert data["message"] == settings.API_STATUS_MSG
