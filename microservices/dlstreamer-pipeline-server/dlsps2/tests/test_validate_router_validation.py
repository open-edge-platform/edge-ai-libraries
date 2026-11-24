# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for path-parameter allowlist validation on the /validate router."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import validate as validate_router


def _client():
    app = FastAPI()
    app.include_router(validate_router.router)
    return TestClient(app)


class TestValidationIdPathValidation:

    def test_rejects_non_uuid_validation_id(self):
        client = _client()

        response = client.get("/validate/status/not-a-valid-id")

        assert response.status_code == 422

    def test_rejects_path_traversal_validation_id(self):
        client = _client()

        response = client.get("/validate/status/etc%2Fpasswd")

        assert response.status_code == 422

    def test_accepts_well_formed_uuid_and_reaches_handler(self):
        client = _client()

        # No pipeline manager configured -> handler raises 503, proving the
        # request passed path-param validation and reached the handler.
        response = client.get("/validate/status/a6d67224-eacc-41ec-9f36-0242c0a86003")

        assert response.status_code == 503
