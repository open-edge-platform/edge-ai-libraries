"""B4.5 — HarnessCompressor + real lingua server integration tests.

These tests hit a running lingua server. Default URL is read from env
``LINGUA_INTEGRATION_URL`` (fallback ``http://localhost:8001/compress``);
all tests are skipped if the server is unreachable.

Quick start (one of):

  # docker compose
  cd deployment/lingua && docker-compose up -d --build

  # bare metal
  python -m adaptive_token_compressor.model_servers.lingua.apply_patch
    python -m adaptive_token_compressor.model_servers.lingua --backend pytorch --device xpu

Then run:

  pytest tests/harness/test_lingua_integration.py -v

Coverage matches plan §17.3 B4.5 gate:
  - end-to-end compress with real backend (basic + openclaw fixture)
  - cache hit path (CompressionManager-injected cache, second call → hit)
  - workspace path normalization round-trip
  - backend error fallback (point harness at bogus URL → original kept)
  - health check forwards to backend.health_check
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import cachetools
import pytest
import requests

from adaptive_token_compressor.core.base import CompressionContext
from adaptive_token_compressor.core.health import HealthState
from adaptive_token_compressor.core.metrics import CompressionScope
from adaptive_token_compressor.harness.compressor import HarnessCompressor


LINGUA_URL = os.environ.get(
    "LINGUA_INTEGRATION_URL", "http://localhost:8001/compress"
)
LINGUA_HEALTH = LINGUA_URL.rsplit("/", 1)[0] + "/health"


def _server_reachable() -> bool:
    """Probe the configured lingua server. Skip the whole module if down."""
    try:
        resp = requests.get(LINGUA_HEALTH, timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _server_reachable(),
    reason=(
        f"Lingua server not reachable at {LINGUA_HEALTH}. "
        "Start it via deployment/lingua/docker-compose.yaml or "
        "`python -m adaptive_token_compressor.model_servers.lingua`."
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPENCLAW_SAMPLE = _REPO_ROOT / "dev_tests" / "output" / "01_raw.txt"


@pytest.fixture(scope="module")
def openclaw_prompt() -> str:
    """Real-world OpenClaw system prompt (~27KB) for end-to-end coverage."""
    if not _OPENCLAW_SAMPLE.exists():
        pytest.skip(f"OpenClaw sample missing at {_OPENCLAW_SAMPLE}")
    return _OPENCLAW_SAMPLE.read_text(encoding="utf-8")


def _make_compressor(**overrides) -> HarnessCompressor:
    """Default integration compressor pointing at the running server."""
    kwargs = dict(
        profile="openclaw",
        lingua_url=LINGUA_URL,
        compress_rate=0.5,
        compress_min_chars=500,
        timeout=60.0,
    )
    kwargs.update(overrides)
    return HarnessCompressor(**kwargs)


def _make_long_content(prefix: str = "", n_chars: int = 1500) -> str:
    """Long enough to exceed compress_min_chars and have something to compress."""
    body = (
        "The quick brown fox jumps over the lazy dog. "
        "LLMLingua-2 is a token compression model based on BERT. "
    ) * (n_chars // 100 + 1)
    return prefix + body[:n_chars]


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end compression
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndCompression:
    def test_basic_long_prompt_compresses(self):
        comp = _make_compressor(profile="generic", compress_min_chars=200)
        ctx = CompressionContext(
            messages=[{"role": "system", "content": _make_long_content("", 1500)}],
            tools=None,
        )
        result = comp.compress(ctx)

        assert result.metrics.scope == CompressionScope.HARNESS
        assert result.metrics.tokens_after > 0
        # Real server should genuinely shrink generic English prose.
        assert result.metrics.tokens_after < result.metrics.tokens_before
        assert result.metrics.error is None
        assert result.metrics.skip_reason is None

    def test_short_prompt_skipped_without_calling_server(self):
        comp = _make_compressor(compress_min_chars=500)
        ctx = CompressionContext(
            messages=[{"role": "system", "content": "Short prompt."}],
            tools=None,
        )
        result = comp.compress(ctx)
        assert result.messages[0]["content"] == "Short prompt."
        assert result.metrics.skip_reason == "min_chars"
        assert result.metrics.error is None

    def test_openclaw_real_prompt_end_to_end(self, openclaw_prompt):
        """The 27KB real OpenClaw prompt should round-trip through real server."""
        comp = _make_compressor()
        ctx = CompressionContext(
            messages=[{"role": "system", "content": openclaw_prompt}],
            tools=None,
        )
        result = comp.compress(ctx)
        assert result.metrics.error is None
        assert result.metrics.tokens_before > 1000
        # Some sections (preserve_headings) keep verbatim, but at least one
        # compressible section should have shrunk.
        assert result.metrics.tokens_after < result.metrics.tokens_before

        details = result.metrics.details["section_details"]
        assert len(details) > 1, "openclaw profile should split into multiple sections"
        compressed = [d for d in details if d.compressed]
        preserved = [d for d in details if not d.compressed and d.backend_error is None]
        assert compressed, "at least one section should compress"
        assert preserved, "at least one section should be preserved verbatim"

    def test_workspace_path_restored_in_output(self):
        """WorkspaceNormalizer must put the original workspace path back.

        Requires the placeholder to survive lingua compression intact —
        which works because ``HarnessCompressor`` passes
        ``force_tokens=normalizer.placeholders()`` to the backend so BERT's
        multilingual tokenizer keeps ``__AGENT_WORKSPACE__`` as a single
        token rather than splitting it into ``_ AGENT _ WORKSPACE _``.
        """
        comp = _make_compressor(profile="openclaw", compress_min_chars=200)
        body = (
            "Files in /home/alice/.openclaw/workspace_a are listed below. "
            "Path appears multiple times here as well: "
            "/home/alice/.openclaw/workspace_a is the canonical location. "
        ) * 30
        ctx = CompressionContext(
            messages=[{"role": "system", "content": body}], tools=None
        )
        result = comp.compress(ctx)
        out = result.messages[0]["content"]
        # Restore must run — placeholder must not leak into output.
        assert "__AGENT_WORKSPACE__" not in out
        # Original path retained (tokens around it may be dropped by lingua,
        # but the path itself is restored wherever a placeholder survived).
        assert "/home/alice/.openclaw/workspace_a" in out

    def test_non_harness_role_passthrough(self):
        comp = _make_compressor(compress_min_chars=200)
        long_text = _make_long_content("", 1500)
        ctx = CompressionContext(
            messages=[
                {"role": "user", "content": long_text},
                {"role": "assistant", "content": long_text},
            ],
            tools=None,
        )
        result = comp.compress(ctx)
        # User / assistant must be left alone.
        assert result.messages[0]["content"] == long_text
        assert result.messages[1]["content"] == long_text


# ─────────────────────────────────────────────────────────────────────────────
# Cache hit path (manager-injected cache; same content twice)
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheHitPath:
    def test_second_call_hits_cache_byte_identical(self):
        comp = _make_compressor(profile="generic", compress_min_chars=200)
        comp.set_cache(cachetools.LRUCache(maxsize=64), threading.Lock())

        ctx = CompressionContext(
            messages=[{"role": "system", "content": _make_long_content("", 1500)}],
            tools=None,
        )

        # First call: cache miss, real server invocation.
        r1 = comp.compress(ctx)
        assert r1.metrics.details["cache_hits"] == 0
        out1 = r1.messages[0]["content"]

        # Second call with identical input: cache hit.
        r2 = comp.compress(ctx)
        assert r2.metrics.details["cache_hits"] >= 1
        out2 = r2.messages[0]["content"]

        # Byte-identical outputs — required for downstream prefix-cache stability.
        assert out1 == out2

    def test_repeated_compress_byte_identical_real_server(self):
        """N=5 identical inputs through real lingua: outputs byte-identical.

        Cache absorbs BERT's potential floating-point wobble: only the first
        call hits the server; subsequent calls return the cached compressed
        text. Verifies the prefix-cache-stability contract end-to-end with
        the real backend rather than a deterministic fake.
        """
        comp = _make_compressor(profile="generic", compress_min_chars=200)
        comp.set_cache(cachetools.LRUCache(maxsize=64), threading.Lock())

        ctx = CompressionContext(
            messages=[
                {"role": "system", "content": _make_long_content("Stable: ", 1500)}
            ],
            tools=None,
        )

        N = 5
        results = [comp.compress(ctx) for _ in range(N)]
        outputs = [r.messages[0]["content"] for r in results]

        # First call cache-miss; subsequent 4 must hit.
        assert results[0].metrics.details["cache_hits"] == 0
        for i in range(1, N):
            assert results[i].metrics.details["cache_hits"] >= 1, (
                f"call #{i+1} did not register a cache hit"
            )

        # Every output byte-identical to the first.
        first = outputs[0]
        for i, out in enumerate(outputs[1:], start=2):
            assert out == first, f"output #{i} diverged from #1"

    def test_cache_hit_with_workspace_normalization(self):
        """Two prompts differing only in workspace path → second hits cache."""
        comp = _make_compressor(profile="openclaw", compress_min_chars=200)
        comp.set_cache(cachetools.LRUCache(maxsize=64), threading.Lock())

        body = (
            "Files in {ws} are loaded. Tool descriptions follow. "
            "The workspace at {ws} contains many helpers. "
        ) * 25

        ctx_a = CompressionContext(
            messages=[
                {
                    "role": "system",
                    "content": body.format(ws="/home/alice/.openclaw/workspace_a"),
                }
            ],
            tools=None,
        )
        ctx_b = CompressionContext(
            messages=[
                {
                    "role": "system",
                    "content": body.format(ws="/home/bob/.openclaw/workspace_b"),
                }
            ],
            tools=None,
        )

        r1 = comp.compress(ctx_a)
        r2 = comp.compress(ctx_b)
        # Workspace path normalised in cache key → second user hits cache.
        assert r2.metrics.details["cache_hits"] >= 1
        # Each session sees its own workspace path restored (force_tokens keeps
        # the placeholder atomic so restore can find and replace it).
        assert "/home/alice/.openclaw/workspace_a" in r1.messages[0]["content"]
        assert "/home/bob/.openclaw/workspace_b" in r2.messages[0]["content"]
        # Each session sees its own workspace path restored.
        assert "/home/alice/.openclaw/workspace_a" in r1.messages[0]["content"]
        assert "/home/bob/.openclaw/workspace_b" in r2.messages[0]["content"]


# ─────────────────────────────────────────────────────────────────────────────
# Backend error fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestBackendErrorFallback:
    def test_unreachable_backend_keeps_original(self):
        """Wrong port → BackendError caught per-section, original kept."""
        # Pick a port unlikely to be a server.
        comp = _make_compressor(
            profile="generic",
            lingua_url="http://localhost:1/compress",
            compress_min_chars=200,
            timeout=2.0,
        )
        content = _make_long_content("", 1500)
        ctx = CompressionContext(
            messages=[{"role": "system", "content": content}], tools=None
        )
        result = comp.compress(ctx)
        # compress() never raises.
        assert result is not None
        # Section-level fallback: original content preserved.
        assert result.messages[0]["content"] == content
        # Error surfaced via metrics.error (top-level concatenation).
        assert result.metrics.error is not None
        # Per-section error recorded too.
        details = result.metrics.details["section_details"]
        assert any(d.backend_error is not None for d in details)


# ─────────────────────────────────────────────────────────────────────────────
# Health check forwarding
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthCheckForwarding:
    def test_health_check_returns_healthy_for_running_server(self):
        comp = _make_compressor()
        status = comp.health_check(timeout=5.0)
        assert status.state is HealthState.HEALTHY

    def test_health_check_unhealthy_for_bogus_url(self):
        comp = _make_compressor(lingua_url="http://localhost:1/compress", timeout=2.0)
        status = comp.health_check(timeout=2.0)
        assert status.state is HealthState.UNHEALTHY
