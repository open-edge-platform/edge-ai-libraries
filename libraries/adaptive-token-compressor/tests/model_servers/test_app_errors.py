"""Security regression tests for Compress Server error responses."""
from __future__ import annotations

import argparse
import sys
import types

from fastapi.testclient import TestClient

from adaptive_token_compressor.model_servers.compress_server.app import build_app


class _FakeModel:
    def parameters(self):
        return iter([types.SimpleNamespace(device="cpu")])


class _FakePromptCompressor:
    def __init__(self, **_: object):
        self.model = _FakeModel()
        self.device = "cpu"


class _FailingPromptCompressor(_FakePromptCompressor):
    def compress_prompt(self, *_: object, **__: object):
        raise RuntimeError("sensitive compressor detail")


def test_unexpected_error_response_is_generic(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "llmlingua",
        types.SimpleNamespace(PromptCompressor=_FakePromptCompressor),
    )
    app = build_app(
        argparse.Namespace(
            runtime="pytorch",
            device="cpu",
            device_index=0,
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


def test_compression_error_response_is_generic(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "llmlingua",
        types.SimpleNamespace(PromptCompressor=_FailingPromptCompressor),
    )
    app = build_app(
        argparse.Namespace(
            runtime="pytorch",
            device="cpu",
            device_index=0,
            model_name_id="",
            mode="llmlingua2",
        )
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        "/compress", json={"text": "hello"}
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "compression failed for the given parameters"
    }
    assert "sensitive compressor detail" not in response.text