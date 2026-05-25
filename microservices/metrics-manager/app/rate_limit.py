# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Rate limiting middleware for API protection.

Implements a token bucket algorithm for rate limiting with
configurable limits per client IP address.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from .logging_config import get_logger
from .settings import get_settings

logger = get_logger("rate_limit")


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""

    capacity: int
    tokens: float = field(init=False)
    last_update: float = field(default_factory=time.monotonic)
    refill_rate: float = field(init=False)  # tokens per second

    def __post_init__(self):
        self.tokens = float(self.capacity)
        settings = get_settings()
        # Refill rate: requests_per_minute / 60 = tokens per second
        self.refill_rate = settings.rate_limit_requests_per_minute / 60.0

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.

        Returns True if successful, False if rate limited.
        """
        now = time.monotonic()
        time_passed = now - self.last_update
        self.last_update = now

        # Refill tokens based on time passed
        self.tokens = min(self.capacity, self.tokens + time_passed * self.refill_rate)

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def get_retry_after(self) -> float:
        """Get seconds until a token is available."""
        if self.tokens >= 1:
            return 0.0
        tokens_needed = 1 - self.tokens
        return tokens_needed / self.refill_rate


class RateLimiter:
    """
    IP-based rate limiter using token bucket algorithm.

    Maintains separate buckets for each client IP with automatic
    cleanup of stale entries.
    """

    def __init__(self, capacity: int | None = None):
        settings = get_settings()
        self.capacity = capacity or settings.rate_limit_burst
        self.buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(capacity=self.capacity)
        )
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 300  # Clean up every 5 minutes

    def is_allowed(self, client_ip: str) -> tuple[bool, float]:
        """
        Check if request from client IP is allowed.

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        self._maybe_cleanup()

        bucket = self.buckets[client_ip]
        if bucket.consume():
            return True, 0.0
        return False, bucket.get_retry_after()

    def _maybe_cleanup(self) -> None:
        """Clean up stale buckets periodically."""
        now = time.monotonic()
        if now - self._last_cleanup > self._cleanup_interval:
            self._last_cleanup = now
            # Remove buckets that have been full for a while (inactive clients)
            cutoff = now - self._cleanup_interval
            stale_keys = [
                ip for ip, bucket in self.buckets.items()
                if bucket.last_update < cutoff and bucket.tokens >= bucket.capacity
            ]
            for key in stale_keys:
                del self.buckets[key]
            if stale_keys:
                logger.debug(
                    "Cleaned up stale rate limit buckets", extra={"count": len(stale_keys)}
                )


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the rate limiter (for testing)."""
    global _rate_limiter
    _rate_limiter = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Applies rate limiting based on client IP address.
    Excludes health check endpoints from rate limiting.
    """

    # Endpoints exempt from rate limiting:
    # - /health, /api/health: liveness/readiness probes (must always succeed)
    # - /metrics: Prometheus scrape endpoint (scraped by collectors at high rate)
    # - /:        root health page
    EXEMPT_PATHS = {"/health", "/api/health", "/metrics", "/"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()

        # Skip if rate limiting is disabled
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # Skip rate limiting for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Get client IP
        client_ip = self._get_client_ip(request)

        # Check rate limit
        rate_limiter = get_rate_limiter()
        is_allowed, retry_after = rate_limiter.is_allowed(client_ip)

        if not is_allowed:
            logger.warning("Rate limit exceeded", extra={"client_ip": client_ip})
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        response = await call_next(request)
        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request.

        Proxy headers (X-Forwarded-For, X-Real-IP) are only honoured when
        ``trust_forwarded_headers`` is enabled in settings.  Without this flag
        an attacker could spoof their IP by injecting these headers and bypass
        per-IP rate limiting.
        """
        settings = get_settings()
        if settings.trust_forwarded_headers:
            # Check X-Forwarded-For header (from reverse proxies)
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                # Take the first IP in the chain
                return forwarded_for.split(",")[0].strip()

            # Check X-Real-IP header
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                return real_ip.strip()

        # Fall back to direct client IP
        if request.client:
            return request.client.host

        return "unknown"
