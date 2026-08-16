"""Tests for core/backends.py — covers plan §13 row `core/backends`."""
from __future__ import annotations

import pytest
import responses

from adaptive_token_compressor.core.backends import (
    CompressionBackend,
    LinguaHTTPBackend,
    NoopBackend,
)
from adaptive_token_compressor.core.exceptions import BackendError
from adaptive_token_compressor.core.health import HealthState


# ─────────────────────────────────────────────────────────────────────────────
# CompressionBackend Protocol
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressionBackendProtocol:
    def test_runtime_checkable_lingua_backend(self):
        backend = LinguaHTTPBackend()
        assert isinstance(backend, CompressionBackend)

    def test_runtime_checkable_noop_backend(self):
        backend = NoopBackend()
        assert isinstance(backend, CompressionBackend)

    def test_object_without_methods_fails(self):
        class NotABackend:
            pass

        assert not isinstance(NotABackend(), CompressionBackend)


# ─────────────────────────────────────────────────────────────────────────────
# NoopBackend
# ─────────────────────────────────────────────────────────────────────────────


class TestNoopBackend:
    def test_compress_returns_input_verbatim(self):
        backend = NoopBackend()
        text = "Some prompt content here."
        result = backend.compress(text, rate=0.5)
        assert result == text

    def test_compress_ignores_rate(self):
        backend = NoopBackend()
        text = "x"
        assert backend.compress(text, rate=0.3) == text
        assert backend.compress(text, rate=0.9) == text

    def test_compress_ignores_digit_kwargs(self):
        backend = NoopBackend()
        text = "42 tokens"
        result = backend.compress(
            text, rate=0.5, force_reserve_digit=True, digit_neighbor_radius=3
        )
        assert result == text

    def test_health_check_returns_healthy(self):
        backend = NoopBackend()
        status = backend.health_check()
        assert status.state is HealthState.HEALTHY
        assert status.component == "noop_backend"


# ─────────────────────────────────────────────────────────────────────────────
# LinguaHTTPBackend.__init__
# ─────────────────────────────────────────────────────────────────────────────


class TestLinguaHTTPBackendInit:
    def test_default_lingua_url(self):
        backend = LinguaHTTPBackend()
        assert backend._lingua_url == "http://localhost:8001/compress"

    def test_custom_lingua_url(self):
        backend = LinguaHTTPBackend(lingua_url="http://example.com:9000/compress")
        assert backend._lingua_url == "http://example.com:9000/compress"

    def test_health_endpoint_derived_from_lingua_url(self):
        backend = LinguaHTTPBackend(lingua_url="http://example.com:8001/compress")
        assert backend._health_endpoint == "http://example.com:8001/health"

    def test_health_endpoint_explicit(self):
        backend = LinguaHTTPBackend(health_endpoint="http://custom.com/status")
        assert backend._health_endpoint == "http://custom.com/status"

    def test_health_endpoint_strips_trailing_slash_and_compress(self):
        backend = LinguaHTTPBackend(lingua_url="http://example.com:8001/compress/")
        assert backend._health_endpoint == "http://example.com:8001/health"


# ─────────────────────────────────────────────────────────────────────────────
# LinguaHTTPBackend.compress — success paths
# ─────────────────────────────────────────────────────────────────────────────


class TestLinguaHTTPBackendCompressSuccess:
    @responses.activate
    def test_compressed_prompt_returned(self):
        responses.post(
            "http://localhost:8001/compress",
            json={"compressed_prompt": "short prompt"},
            status=200,
        )
        backend = LinguaHTTPBackend()
        result = backend.compress("original long prompt", rate=0.5)
        assert result == "short prompt"

    @responses.activate
    def test_compressed_text_fallback(self):
        responses.post(
            "http://localhost:8001/compress",
            json={"compressed_text": "short text"},
            status=200,
        )
        backend = LinguaHTTPBackend()
        result = backend.compress("original", rate=0.6)
        assert result == "short text"

    @responses.activate
    def test_compressed_prompt_preferred_over_compressed_text(self):
        responses.post(
            "http://localhost:8001/compress",
            json={"compressed_prompt": "A", "compressed_text": "B"},
            status=200,
        )
        backend = LinguaHTTPBackend()
        result = backend.compress("original", rate=0.5)
        assert result == "A"

    @responses.activate
    def test_sends_all_four_body_fields(self):
        responses.post(
            "http://localhost:8001/compress",
            json={"compressed_prompt": "ok"},
        )
        backend = LinguaHTTPBackend()
        backend.compress(
            "text", rate=0.4, force_reserve_digit=True, digit_neighbor_radius=2
        )
        assert len(responses.calls) == 1
        import json

        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body == {
            "text": "text",
            "rate": 0.4,
            "force_reserve_digit": True,
            "digit_neighbor_radius": 2,
        }

    @responses.activate
    def test_sends_default_digit_kwargs(self):
        responses.post(
            "http://localhost:8001/compress",
            json={"compressed_prompt": "ok"},
        )
        backend = LinguaHTTPBackend()
        backend.compress("text", rate=0.5)
        import json

        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["force_reserve_digit"] is False
        assert sent_body["digit_neighbor_radius"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# LinguaHTTPBackend.compress — error paths
# ─────────────────────────────────────────────────────────────────────────────


class TestLinguaHTTPBackendCompressErrors:
    @responses.activate
    def test_http_500_raises_backend_error(self):
        responses.post("http://localhost:8001/compress", status=500)
        backend = LinguaHTTPBackend()
        with pytest.raises(BackendError, match="backend request failed"):
            backend.compress("text", rate=0.5)

    @responses.activate
    def test_http_404_raises_backend_error(self):
        responses.post("http://localhost:8001/compress", status=404)
        backend = LinguaHTTPBackend()
        with pytest.raises(BackendError, match="backend request failed"):
            backend.compress("text", rate=0.5)

    @responses.activate
    def test_timeout_raises_backend_error(self):
        import requests as req_lib

        # responses library: body=Exception triggers the exception during send
        responses.post(
            "http://localhost:8001/compress", body=req_lib.Timeout("Connection timeout")
        )
        backend = LinguaHTTPBackend()
        with pytest.raises(BackendError, match="backend request failed"):
            backend.compress("text", rate=0.5)

    @responses.activate
    def test_invalid_json_raises_backend_error(self):
        responses.post("http://localhost:8001/compress", body="not json", status=200)
        backend = LinguaHTTPBackend()
        with pytest.raises(BackendError, match="backend returned invalid response"):
            backend.compress("text", rate=0.5)

    @responses.activate
    def test_empty_compressed_prompt_raises_backend_error(self):
        responses.post(
            "http://localhost:8001/compress",
            json={"compressed_prompt": ""},
            status=200,
        )
        backend = LinguaHTTPBackend()
        with pytest.raises(BackendError, match="missing compressed_prompt"):
            backend.compress("text", rate=0.5)

    @responses.activate
    def test_missing_both_fields_raises_backend_error(self):
        responses.post(
            "http://localhost:8001/compress",
            json={"other_field": "x"},
            status=200,
        )
        backend = LinguaHTTPBackend()
        with pytest.raises(BackendError, match="missing compressed_prompt"):
            backend.compress("text", rate=0.5)


# ─────────────────────────────────────────────────────────────────────────────
# LinguaHTTPBackend.health_check
# ─────────────────────────────────────────────────────────────────────────────


class TestLinguaHTTPBackendHealthCheck:
    @responses.activate
    def test_status_ok_returns_healthy(self):
        responses.get(
            "http://localhost:8001/health",
            json={"status": "ok", "model": "llmlingua2"},
            status=200,
        )
        backend = LinguaHTTPBackend()
        status = backend.health_check()
        assert status.state is HealthState.HEALTHY
        assert "backend@http://localhost:8001/compress" in status.component

    @responses.activate
    def test_failure_message_does_not_expose_exception_details(self):
        secret = "https://user:secret@example.test/health"
        responses.get("http://localhost:8001/health", body=RuntimeError(secret))
        status = LinguaHTTPBackend().health_check()
        assert status.state is HealthState.UNHEALTHY
        assert status.message == "backend unavailable"
        assert secret not in status.message

    @responses.activate
    def test_status_loading_returns_degraded(self):
        responses.get(
            "http://localhost:8001/health",
            json={"status": "loading"},
            status=200,
        )
        backend = LinguaHTTPBackend()
        status = backend.health_check()
        assert status.state is HealthState.DEGRADED
        assert "status=loading" in status.message

    @responses.activate
    def test_http_500_returns_unhealthy(self):
        responses.get("http://localhost:8001/health", status=500)
        backend = LinguaHTTPBackend()
        status = backend.health_check()
        assert status.state is HealthState.UNHEALTHY

    @responses.activate
    def test_connection_error_returns_unhealthy(self):
        import requests as req_lib

        responses.get(
            "http://localhost:8001/health", body=req_lib.ConnectionError("Connection refused")
        )
        backend = LinguaHTTPBackend()
        status = backend.health_check()
        assert status.state is HealthState.UNHEALTHY

    @responses.activate
    def test_custom_timeout_passed(self):
        responses.get("http://localhost:8001/health", json={"status": "ok"})
        backend = LinguaHTTPBackend()
        status = backend.health_check(timeout=1.0)
        assert status.state is HealthState.HEALTHY
