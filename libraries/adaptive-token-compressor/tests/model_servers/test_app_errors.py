"""Security regression tests for Lingua server error responses."""
from __future__ import annotations

import argparse
import sys
import types

from fastapi.testclient import TestClient

from adaptive_token_compressor.model_servers.lingua.app import build_app


class _FakeModel:
    def parameters(self):
        return iter([types.SimpleNamespace(device="cpu")])


class _FakePromptCompressor:
    def __init__(self, **_: object):
        self.model = _FakeModel()
        self.device = "cpu"


def test_unexpected_error_response_is_generic(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "llmlingua",
        types.SimpleNamespace(PromptCompressor=_FakePromptCompressor),
    )
    app = build_app(
        argparse.Namespace(
            backend="pytorch",
            device="cpu",
            xpu_index=0,
            model_name_id="",
            mode="llmlingua2",
        )
    )

    @app.get("/raise-unexpected")
    async def raise_unexpected():
        raise RuntimeError("token=super-secret")

    response = TestClient(app, raise_server_exceptions=False).get("/raise-unexpected")

    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "super-secret" not in response.text