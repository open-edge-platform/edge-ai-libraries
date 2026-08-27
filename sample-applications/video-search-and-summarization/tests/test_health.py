# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Functional test — VSS health check.

Verifies that the Pipeline Manager is reachable and reports healthy
through the nginx gateway at GET /manager/health.
"""

import pytest
import requests


class TestHealth:

    def test_pipeline_manager_health(self, base_url, vss_health):
        """GET /manager/health must return HTTP 200."""
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        response = requests.get(f"{base_url}/manager/health", timeout=10)

        assert response.status_code == 200, (
            f"Expected 200 from /manager/health, got {response.status_code}. "
            f"Response: {response.text}"
        )

    def test_pipeline_manager_health_response_body(self, base_url, vss_health):
        """GET /manager/health response body must indicate a healthy state."""
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        response = requests.get(f"{base_url}/manager/health", timeout=10)
        assert response.status_code == 200

        body = response.json()
        # Pipeline Manager returns {"status": "ok"} when healthy.
        assert "status" in body, f"No 'status' field in health response: {body}"
        assert body["status"].lower() in ("ok", "healthy"), (
            f"Unexpected health status: {body['status']}"
        )
