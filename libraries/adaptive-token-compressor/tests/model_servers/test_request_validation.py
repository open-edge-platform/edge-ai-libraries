# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Input-validation hardening for the Lingua `/compress` interface (ATC-SEC-002).

Canonical, hermetic spec for `CompressRequest` and the server's rejection
behavior — independent of the fuzzing deliverable. Two layers:

* **Model layer** — `CompressRequest` accepts well-formed input and rejects
  every out-of-contract shape (``extra=forbid``, bounds, strict bool, mode enum).
  Pure pydantic; no app build, no model load, no network.
* **HTTP layer** — the two properties the model alone cannot express: the
  ``LINGUA_MAX_TEXT_CHARS`` size cap (413, DoS guard) and the generic 422 body
  that never echoes attacker-controlled values back to the client.
"""
from __future__ import annotations

import argparse
import sys
import types

import pytest
from pydantic import ValidationError

from adaptive_token_compressor.model_servers.lingua import app as app_module
from adaptive_token_compressor.model_servers.lingua.app import CompressRequest


# ─────────────────────────────────────────────────────────────────────────────
# Model layer — CompressRequest schema
# ─────────────────────────────────────────────────────────────────────────────


class TestValidRequests:
    def test_minimal_defaults(self):
        r = CompressRequest(text="hello world")
        assert r.rate == 0.33
        assert r.digit_neighbor_radius == 0
        assert r.force_reserve_digit is False
        assert r.force_tokens is None
        assert r.mode is None

    def test_all_fields_populated(self):
        r = CompressRequest(
            text="hello",
            mode="llmlingua2",
            rate=0.5,
            force_tokens=["a", "b"],
            force_reserve_digit=True,
            digit_neighbor_radius=3,
        )
        assert r.mode == "llmlingua2"
        assert r.force_tokens == ["a", "b"]

    def test_force_tokens_at_limit_ok(self):
        # 100 is the boundary; must not regress to a rejection.
        assert len(CompressRequest(text="hi", force_tokens=[""] * 100).force_tokens) == 100

    def test_float_valued_integer_radius_accepted(self):
        # 99.0 is a valid integer per JSON Schema; the bool guard must not reject it.
        assert CompressRequest(text="0", digit_neighbor_radius=99.0).digit_neighbor_radius == 99


class TestRejectedRequests:
    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            CompressRequest(text="hi", evil="x")

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            CompressRequest(text="")

    def test_missing_text_rejected(self):
        with pytest.raises(ValidationError):
            CompressRequest(rate=0.5)

    @pytest.mark.parametrize("rate", [0.0, -0.1, 1.5])
    def test_rate_out_of_range_rejected(self, rate):
        with pytest.raises(ValidationError):
            CompressRequest(text="hi", rate=rate)

    def test_force_tokens_over_limit_rejected(self):
        # >100 previously tripped a bare assert deep in LLMLingua -> HTTP 500.
        with pytest.raises(ValidationError):
            CompressRequest(text="0", force_tokens=[""] * 101)

    def test_unknown_mode_rejected(self):
        with pytest.raises(ValidationError):
            CompressRequest(text="hi", mode="nope")

    @pytest.mark.parametrize("radius", [-1, 101])
    def test_digit_radius_out_of_range_rejected(self, radius):
        with pytest.raises(ValidationError):
            CompressRequest(text="0", digit_neighbor_radius=radius)

    def test_bool_not_accepted_as_digit_radius(self):
        # bool is a subclass of int; the explicit validator rejects it.
        with pytest.raises(ValidationError):
            CompressRequest(text="0", digit_neighbor_radius=False)

    def test_int_not_accepted_as_force_reserve_digit(self):
        # strict=True forbids int->bool coercion.
        with pytest.raises(ValidationError):
            CompressRequest(text="0", force_reserve_digit=0)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP layer — size cap (413) and no-echo generic 422
# ─────────────────────────────────────────────────────────────────────────────


class _FakeModel:
    def parameters(self):
        return iter([types.SimpleNamespace(device="cpu")])


class _FakePromptCompressor:
    def __init__(self, **_: object):
        self.model = _FakeModel()
        self.device = "cpu"


@pytest.fixture
def client(monkeypatch):
    """A TestClient over a built app with torch/llmlingua stubbed out.

    The compression model is never invoked by these tests: the 413 check
    short-circuits before compression, and 422 fails at request validation
    before the handler body runs.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "llmlingua",
        types.SimpleNamespace(PromptCompressor=_FakePromptCompressor),
    )
    app = app_module.build_app(
        argparse.Namespace(
            backend="pytorch",
            device="cpu",
            xpu_index=0,
            model_name_id="",
            mode="llmlingua2",
        )
    )
    return TestClient(app, raise_server_exceptions=False)


def test_oversized_text_rejected_with_413(client, monkeypatch):
    # DoS guard: text over LINGUA_MAX_TEXT_CHARS is rejected before compression.
    monkeypatch.setattr(app_module, "MAX_TEXT_CHARS", 10)
    resp = client.post("/compress", json={"text": "x" * 50})
    assert resp.status_code == 413
    assert resp.json() == {"detail": "text too large"}


def test_invalid_body_returns_generic_422_without_echo(client):
    # An attacker-controlled value in a rejected field must NOT appear in the
    # response body — it stays the generic, schema-shaped HTTPValidationError.
    secret_marker = "PEEKABOO-INJECTED-VALUE"
    resp = client.post("/compress", json={"text": "hi", "evil": secret_marker})
    assert resp.status_code == 422
    assert resp.json() == {
        "detail": [{"loc": [], "msg": "invalid request parameters", "type": "validation_error"}]
    }
    assert secret_marker not in resp.text