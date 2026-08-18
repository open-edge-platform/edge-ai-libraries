# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Trust-boundary posture of the Lingua server (ATC-SEC-003).

The Lingua model server is **unauthenticated by design** — it is meant to run on
a trusted network / behind a gateway, not exposed directly. That is a deliberate
security decision, and these tests *codify* it: if someone later adds an auth
layer (or an auth scheme leaks into the OpenAPI spec) without updating the
documented deployment contract, these assertions break and force the change to
be reviewed.

Hermetic: torch / llmlingua are stubbed; no model is loaded and no network I/O
happens. `/health` returns a static dict and `/compress` rejects at validation,
so neither test path touches the compression model.
"""
from __future__ import annotations

import argparse
import sys
import types

import pytest

from adaptive_token_compressor.model_servers.lingua import app as app_module


class _FakeModel:
    def parameters(self):
        return iter([types.SimpleNamespace(device="cpu")])


class _FakePromptCompressor:
    def __init__(self, **_: object):
        self.model = _FakeModel()
        self.device = "cpu"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "llmlingua",
        types.SimpleNamespace(PromptCompressor=_FakePromptCompressor),
    )
    return app_module.build_app(
        argparse.Namespace(
            backend="pytorch",
            device="cpu",
            xpu_index=0,
            model_name_id="",
            mode="llmlingua2",
        )
    )


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=False)


def test_health_requires_no_auth(client):
    # No Authorization header — must still succeed.
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_compress_is_not_gated_by_auth(client):
    # A request with no credentials reaches request validation (422 for a bad
    # body) rather than being turned away with 401/403. This proves there is no
    # authentication gate in front of the endpoint.
    resp = client.post("/compress", json={"not_a_field": 1})
    assert resp.status_code == 422
    assert resp.status_code not in (401, 403)


def test_auth_header_is_ignored_not_required(client):
    # Presenting a bearer token neither helps nor is required — the endpoint
    # behaves identically with or without it (still validates the body).
    resp = client.post(
        "/compress",
        json={"not_a_field": 1},
        headers={"Authorization": "Bearer whatever"},
    )
    assert resp.status_code == 422


def test_openapi_declares_no_security_scheme(app):
    # By-design: no authN/authZ. If an auth scheme is ever added, it must surface
    # here and the deployment trust-boundary docs must be updated in lockstep.
    schema = app.openapi()
    assert schema.get("components", {}).get("securitySchemes") is None
    assert not schema.get("security")