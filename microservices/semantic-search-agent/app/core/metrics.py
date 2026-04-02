"""Prometheus metrics collection."""

from prometheus_client import Counter, Histogram, Gauge

# Request counters
api_requests_total = Counter(
    "api_requests_total",
    "Total API requests",
    ["endpoint", "method", "status"],
)

# Match type counters
matches_total = Counter(
    "matches_total",
    "Total matches performed",
    ["match_type", "result"],
)

# Latency histograms
request_duration_seconds = Histogram(
    "request_duration_seconds",
    "Request duration in seconds",
    ["endpoint", "method"],
)

vlm_inference_duration_seconds = Histogram(
    "vlm_inference_duration_seconds",
    "VLM inference duration in seconds",
    ["backend"],
)

# Cache metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["operation"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["operation"],
)

# VLM backend health
vlm_backend_available = Gauge(
    "vlm_backend_available",
    "VLM backend availability (1=available, 0=unavailable)",
    ["backend"],
)
