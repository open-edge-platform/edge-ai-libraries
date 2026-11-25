# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for path-parameter allowlist validation on the /pipelines router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import pipelines as pipelines_router


def _client():
    app = FastAPI()
    app.include_router(pipelines_router.router)
    return TestClient(app)


class TestInstanceIdPathValidation:

    def test_rejects_non_uuid_instance_id(self):
        client = _client()

        response = client.get("/pipelines/etc%2Fpasswd")

        # ASGI routing decodes %2F into a literal '/' before route matching,
        # turning this into extra path segments rather than a single
        # instance_id -> 404/405 (no matching route) instead of 422 (pattern
        # rejected). Either way the value never reaches the handler.
        assert response.status_code in (404, 405, 422)

    def test_rejects_malformed_uuid(self):
        client = _client()

        response = client.get("/pipelines/not-a-valid-uuid")

        assert response.status_code == 422

    def test_accepts_well_formed_uuid_and_reaches_handler(self):
        client = _client()

        # No manager configured -> handler itself raises 503, proving the
        # request passed path-param validation and reached the handler.
        response = client.get("/pipelines/a6d67224-eacc-41ec-9f36-0242c0a86003")

        assert response.status_code == 503


class TestNameVersionPathValidation:

    def test_rejects_invalid_characters_in_name(self):
        client = _client()

        response = client.post(
            "/pipelines/weird!name/1.0",
            json={"source": {"uri": "file:///tmp/x"}},
        )

        assert response.status_code == 422

    def test_accepts_valid_name_and_version(self):
        client = _client()

        # Legacy config not loaded -> handler raises 503, proving the request
        # passed path-param validation and reached the handler.
        response = client.post(
            "/pipelines/user_defined_pipelines/pallet_defect_detection",
            json={"source": {"uri": "file:///tmp/x"}},
        )

        assert response.status_code == 503
