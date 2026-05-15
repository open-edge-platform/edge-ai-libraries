# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for rate limiting middleware and token bucket."""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.rate_limit import RateLimiter, RateLimitMiddleware, TokenBucket, get_rate_limiter


class TestTokenBucket:
    """Unit tests for the TokenBucket token-bucket algorithm."""

    def test_new_bucket_is_full(self):
        bucket = TokenBucket(capacity=10)
        assert bucket.tokens == 10.0

    def test_consume_returns_true_when_tokens_available(self):
        bucket = TokenBucket(capacity=10)
        assert bucket.consume() is True

    def test_consume_decrements_tokens(self):
        bucket = TokenBucket(capacity=10)
        bucket.consume()
        assert bucket.tokens == 9.0

    def test_consume_returns_false_when_exhausted(self):
        bucket = TokenBucket(capacity=1)
        bucket.consume()  # Consume the only token
        bucket.tokens = 0.0  # Ensure fully empty (no refill between calls)
        assert bucket.consume() is False

    def test_get_retry_after_is_zero_when_tokens_available(self):
        bucket = TokenBucket(capacity=10)
        assert bucket.get_retry_after() == 0.0

    def test_get_retry_after_is_positive_when_empty(self):
        bucket = TokenBucket(capacity=1)
        bucket.tokens = 0.0
        assert bucket.get_retry_after() > 0.0

    def test_tokens_refill_over_time(self):
        """Tokens increase when time passes (simulate by setting last_update in the past)."""
        import time

        bucket = TokenBucket(capacity=10)
        bucket.tokens = 0.0
        bucket.last_update = time.monotonic() - 60  # 60 seconds ago
        bucket.consume()  # Triggers refill calculation
        assert bucket.tokens > 0


class TestRateLimiter:
    """Unit tests for the RateLimiter IP-based manager."""

    def test_allows_first_request(self):
        limiter = RateLimiter(capacity=10)
        allowed, retry_after = limiter.is_allowed("1.2.3.4")
        assert allowed is True
        assert retry_after == 0.0

    def test_blocks_when_bucket_empty(self):
        limiter = RateLimiter(capacity=1)
        limiter.buckets["1.2.3.4"].tokens = 0.0
        allowed, retry_after = limiter.is_allowed("1.2.3.4")
        assert allowed is False
        assert retry_after > 0.0

    def test_separate_buckets_per_ip(self):
        """Exhausting one IP does not affect another."""
        limiter = RateLimiter(capacity=1)
        limiter.buckets["1.1.1.1"].tokens = 0.0
        allowed, _ = limiter.is_allowed("2.2.2.2")
        assert allowed is True

class TestRateLimitMiddleware:
    """Integration tests for RateLimitMiddleware via the FastAPI app."""

    def test_returns_429_when_rate_limited(self, client: TestClient):
        limiter = get_rate_limiter()
        limiter.buckets["testclient"].tokens = 0.0

        response = client.post(
            "/api/v1/metrics/simple",
            json={"name": "fps", "value": 30.0},
        )
        assert response.status_code == 429
        assert response.json()["detail"] == "Rate limit exceeded"

    def test_retry_after_header_present_on_429(self, client: TestClient):
        limiter = get_rate_limiter()
        limiter.buckets["testclient"].tokens = 0.0

        response = client.post(
            "/api/v1/metrics/simple",
            json={"name": "x", "value": 1},
        )
        assert response.status_code == 429
        assert "retry-after" in response.headers

    def test_health_endpoint_exempt_from_rate_limit(self, client: TestClient):
        limiter = get_rate_limiter()
        limiter.buckets["testclient"].tokens = 0.0

        response = client.get("/health")
        assert response.status_code == 200

    def test_api_health_endpoint_exempt_from_rate_limit(self, client: TestClient):
        limiter = get_rate_limiter()
        limiter.buckets["testclient"].tokens = 0.0

        response = client.get("/api/health")
        assert response.status_code == 200

    def test_x_forwarded_for_used_as_client_ip_when_trusted(self, client: TestClient):
        """When trust_forwarded_headers=True, X-Forwarded-For IP bucket is used."""
        from app.settings import Settings

        limiter = get_rate_limiter()
        limiter.buckets["10.0.0.1"].tokens = 0.0

        trusted_settings = Settings(trust_forwarded_headers=True)
        with patch("app.rate_limit.get_settings", return_value=trusted_settings):
            response = client.post(
                "/api/v1/metrics/simple",
                json={"name": "fps", "value": 30.0},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
        assert response.status_code == 429

    def test_x_real_ip_used_as_client_ip_when_trusted(self, client: TestClient):
        """When trust_forwarded_headers=True and no X-Forwarded-For, X-Real-IP is used."""
        from app.settings import Settings

        limiter = get_rate_limiter()
        limiter.buckets["192.168.1.1"].tokens = 0.0

        trusted_settings = Settings(trust_forwarded_headers=True)
        with patch("app.rate_limit.get_settings", return_value=trusted_settings):
            response = client.post(
                "/api/v1/metrics/simple",
                json={"name": "fps", "value": 30.0},
                headers={"X-Real-IP": "192.168.1.1"},
            )
        assert response.status_code == 429

    def test_x_forwarded_for_ignored_when_not_trusted(self, client: TestClient):
        """When trust_forwarded_headers=False (default), X-Forwarded-For is ignored."""
        from app.settings import Settings

        limiter = get_rate_limiter()
        # Exhaust the spoofed IP bucket — should have no effect on rate-limiting
        limiter.buckets["1.2.3.4"].tokens = 0.0

        untrusted_settings = Settings(trust_forwarded_headers=False)
        with patch("app.rate_limit.get_settings", return_value=untrusted_settings):
            response = client.post(
                "/api/v1/metrics/simple",
                json={"name": "fps", "value": 30.0},
                headers={"X-Forwarded-For": "1.2.3.4"},
            )
        # Request should succeed because the real client IP ("testclient") has tokens
        assert response.status_code == 202

    def test_requests_succeed_when_tokens_available(self, client: TestClient):
        response = client.post(
            "/api/v1/metrics/simple",
            json={"name": "fps", "value": 30.0},
        )
        assert response.status_code == 202

    def test_rate_limit_disabled_passes_all_requests(self, client: TestClient):
        """Line 151: when rate_limit_enabled=False, dispatch skips limiting."""
        from app.settings import Settings

        mock_settings = Settings(rate_limit_enabled=False)
        with patch("app.rate_limit.get_settings", return_value=mock_settings):
            response = client.post(
                "/api/v1/metrics/simple",
                json={"name": "fps", "value": 1.0},
            )
        assert response.status_code == 202

    def test_get_client_ip_falls_back_to_unknown_when_no_client(self):
        """Line 196: returns 'unknown' when request.client is None."""
        middleware = RateLimitMiddleware(app=None)
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.client = None
        assert middleware._get_client_ip(mock_request) == "unknown"


class TestRateLimiterCleanup:
    """Tests for _maybe_cleanup."""

    def test_cleanup_removes_stale_inactive_buckets(self):
        """Lines 102-112: stale buckets pruned after cleanup interval."""
        limiter = RateLimiter(capacity=10)
        # Create a bucket for a known IP
        limiter.is_allowed("stale-ip")
        bucket = limiter.buckets["stale-ip"]

        # Simulate the bucket being old and full (inactive)
        old_time = time.monotonic() - 400
        bucket.last_update = old_time
        # Make tokens full so it looks "inactive"
        bucket.tokens = float(bucket.capacity)

        # Force cleanup by backdating _last_cleanup
        limiter._last_cleanup = old_time

        # Trigger cleanup via a new request
        limiter.is_allowed("new-ip")

        assert "stale-ip" not in limiter.buckets

    def test_cleanup_does_not_remove_active_buckets(self):
        """Lines 102-112: active buckets are kept during cleanup."""
        limiter = RateLimiter(capacity=10)
        limiter.is_allowed("active-ip")

        # Backdating last_cleanup but NOT the bucket itself
        limiter._last_cleanup = time.monotonic() - 400
        limiter.is_allowed("trigger-ip")

        assert "active-ip" in limiter.buckets
