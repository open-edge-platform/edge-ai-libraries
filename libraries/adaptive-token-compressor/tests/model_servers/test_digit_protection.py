"""Digit-protection tests (ATC-UNIT-007..014).

Digit protection spans three layers; this file covers the two that are
*not* already exercised by ``tests/core/test_backends.py`` (which already
asserts the ``force_reserve_digit`` / ``digit_neighbor_radius`` payload
serialization and the Noop passthrough):

  1. ``apply_patch`` — marker detection, idempotency, --check exit codes,
     and error paths. Fully deterministic; no model or server needed.
  2. Shipped patch integrity — the bundled ``0001-digit-neighbor-radius.patch``
     targets ``prompt_compressor.py`` and injects the ``_digit_neighbor_radius``
     marker. Packaging guard.
  3. Live-server semantics — with ``force_reserve_digit=True`` + radius, digit
     tokens (and their neighbors) survive compression. Skipped unless a real
     lingua server is reachable (same gate as test_lingua_integration.py).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from adaptive_token_compressor.model_servers.lingua import apply_patch


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — a fake llmlingua source tree so apply_patch never touches the
# real installed package.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_llmlingua_dir(tmp_path, monkeypatch):
    """Return a factory that seeds a temp ``prompt_compressor.py`` and points
    ``apply_patch._llmlingua_dir`` at it."""

    def _make(*, patched: bool) -> Path:
        src = tmp_path / "prompt_compressor.py"
        body = "def _main_compressor(self):\n    pass\n"
        if patched:
            # Marker string apply_patch scans for.
            body += "    _digit_neighbor_radius = getattr(self, '_digit_neighbor_radius', 0)\n"
        src.write_text(body, encoding="utf-8")
        monkeypatch.setattr(apply_patch, "_llmlingua_dir", lambda: tmp_path)
        return tmp_path

    return _make


# ─────────────────────────────────────────────────────────────────────────────
# ATC-UNIT-007 · is_patched — marker detection
# ─────────────────────────────────────────────────────────────────────────────


class TestIsPatched:
    def test_true_when_marker_present(self, fake_llmlingua_dir):
        fake_llmlingua_dir(patched=True)
        assert apply_patch.is_patched() is True

    def test_false_when_marker_absent(self, fake_llmlingua_dir):
        fake_llmlingua_dir(patched=False)
        assert apply_patch.is_patched() is False


# ─────────────────────────────────────────────────────────────────────────────
# ATC-UNIT-008 · main(--check) exit codes
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckMode:
    def test_check_returns_0_when_patched(self, fake_llmlingua_dir, monkeypatch):
        fake_llmlingua_dir(patched=True)
        monkeypatch.setattr(sys, "argv", ["apply_patch", "--check"])
        assert apply_patch.main() == 0

    def test_check_returns_1_when_not_patched(self, fake_llmlingua_dir, monkeypatch):
        fake_llmlingua_dir(patched=False)
        monkeypatch.setattr(sys, "argv", ["apply_patch", "--check"])
        assert apply_patch.main() == 1

    def test_check_does_not_apply(self, fake_llmlingua_dir, monkeypatch):
        fake_llmlingua_dir(patched=False)
        monkeypatch.setattr(sys, "argv", ["apply_patch", "--check"])

        def _boom() -> None:
            raise AssertionError("apply() must not run in --check mode")

        monkeypatch.setattr(apply_patch, "apply", _boom)
        assert apply_patch.main() == 1


# ─────────────────────────────────────────────────────────────────────────────
# ATC-UNIT-009 · main() idempotency — already patched skips apply()
# ─────────────────────────────────────────────────────────────────────────────


class TestIdempotency:
    def test_already_patched_skips_apply(self, fake_llmlingua_dir, monkeypatch, capsys):
        fake_llmlingua_dir(patched=True)
        monkeypatch.setattr(sys, "argv", ["apply_patch"])

        called = {"apply": False}
        monkeypatch.setattr(
            apply_patch, "apply", lambda: called.__setitem__("apply", True)
        )

        rc = apply_patch.main()
        assert rc == 0
        assert called["apply"] is False
        assert "already patched" in capsys.readouterr().out.lower()

    def test_unpatched_invokes_apply(self, fake_llmlingua_dir, monkeypatch):
        fake_llmlingua_dir(patched=False)
        monkeypatch.setattr(sys, "argv", ["apply_patch"])

        called = {"apply": False}
        monkeypatch.setattr(
            apply_patch, "apply", lambda: called.__setitem__("apply", True)
        )

        rc = apply_patch.main()
        assert rc == 0
        assert called["apply"] is True


# ─────────────────────────────────────────────────────────────────────────────
# ATC-UNIT-010 · apply() error paths
# ─────────────────────────────────────────────────────────────────────────────


class TestApplyErrors:
    def test_missing_patch_file_raises(self, fake_llmlingua_dir, monkeypatch, tmp_path):
        fake_llmlingua_dir(patched=False)
        monkeypatch.setattr(apply_patch, "_PATCH_FILE", tmp_path / "does_not_exist.patch")
        with pytest.raises(FileNotFoundError, match="Patch file missing"):
            apply_patch.apply()

    def test_patch_subprocess_failure_exits_2(self, fake_llmlingua_dir, monkeypatch):
        fake_llmlingua_dir(patched=False)
        # Ensure the (real) shipped patch file path check passes.
        assert apply_patch._PATCH_FILE.exists()

        class _Result:
            returncode = 1
            stdout = "hunk failed"
            stderr = "boom"

        monkeypatch.setattr(apply_patch.subprocess, "run", lambda *a, **k: _Result())
        with pytest.raises(SystemExit) as ei:
            apply_patch.apply()
        assert ei.value.code == 2

    def test_apply_runs_patch_in_llmlingua_dir(self, fake_llmlingua_dir, monkeypatch):
        target = fake_llmlingua_dir(patched=False)
        seen = {}

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def _fake_run(cmd, cwd, capture_output, text):
            seen["cmd"] = cmd
            seen["cwd"] = cwd
            return _Result()

        monkeypatch.setattr(apply_patch.subprocess, "run", _fake_run)
        apply_patch.apply()
        assert seen["cwd"] == target
        assert seen["cmd"][0] == "patch"
        assert str(apply_patch._PATCH_FILE) in seen["cmd"]


# ─────────────────────────────────────────────────────────────────────────────
# ATC-UNIT-011 · Shipped patch integrity (packaging guard)
# ─────────────────────────────────────────────────────────────────────────────


class TestShippedPatch:
    def test_patch_file_bundled(self):
        assert apply_patch._PATCH_FILE.exists(), (
            "0001-digit-neighbor-radius.patch must ship inside the package"
        )

    def test_patch_targets_prompt_compressor_and_injects_marker(self):
        text = apply_patch._PATCH_FILE.read_text(encoding="utf-8")
        assert "prompt_compressor.py" in text
        assert apply_patch._MARKER in text
        assert "force_reserve_digit" in text


# ─────────────────────────────────────────────────────────────────────────────
# ATC-UNIT-012..013 · Live-server semantics (integration; skipped if no server)
#
# Gate mirrors tests/harness/test_lingua_integration.py: the whole class is
# skipped unless a lingua server is reachable. Requires the LLMLingua-2 patch
# applied on that server for the neighbor-radius assertion to hold.
# ─────────────────────────────────────────────────────────────────────────────


import requests  # noqa: E402  (kept next to its only user, like the integration suite)

from adaptive_token_compressor.core.backends import LinguaHTTPBackend  # noqa: E402

_LINGUA_URL = os.environ.get("LINGUA_INTEGRATION_URL", "http://localhost:8001/compress")
_LINGUA_HEALTH = _LINGUA_URL.rsplit("/", 1)[0] + "/health"


def _server_reachable() -> bool:
    try:
        return requests.get(_LINGUA_HEALTH, timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(
    not _server_reachable(),
    reason=f"Lingua server not reachable at {_LINGUA_HEALTH}",
)
class TestDigitProtectionLive:
    # Numeric-heavy text; the digit *runs* must survive compression.
    _TEXT = (
        "The deployment target throughput is 4096 requests per second on port "
        "8001, with a p99 latency budget of 250 milliseconds and a cache hit "
        "rate of 0.87 measured across 12 identical runs. The fallback timeout "
        "is 60 seconds and the digit neighbor radius defaults to 3."
    )

    @staticmethod
    def _digit_runs(text: str) -> list[str]:
        import re

        return re.findall(r"\d+", text)

    # Unambiguous standalone integers that must survive when protection is on.
    # (Alphanumerics like "p99" and split decimals like "0.87" are tokenizer
    #  corner cases and are covered by the comparative assertion instead.)
    _CANONICAL = {"4096", "8001", "250"}

    def test_canonical_integers_survive_with_force_reserve_digit(self):
        backend = LinguaHTTPBackend(lingua_url=_LINGUA_URL)
        out = backend.compress(
            self._TEXT, rate=0.3, force_reserve_digit=True, digit_neighbor_radius=0
        )
        got = set(self._digit_runs(out))
        missing = sorted(self._CANONICAL - got)
        assert not missing, f"standalone integers dropped despite protection: {missing}"

    def test_protection_retains_more_digits_than_no_protection(self):
        # The feature's contract: force_reserve_digit=True keeps at least as many
        # distinct digit runs as force_reserve_digit=False at the same rate.
        backend = LinguaHTTPBackend(lingua_url=_LINGUA_URL)
        off = set(self._digit_runs(
            backend.compress(self._TEXT, rate=0.3, force_reserve_digit=False)
        ))
        on = set(self._digit_runs(
            backend.compress(self._TEXT, rate=0.3, force_reserve_digit=True)
        ))
        assert len(on) >= len(off)

    def test_neighbor_radius_keeps_more_context_than_radius_zero(self):
        backend = LinguaHTTPBackend(lingua_url=_LINGUA_URL)
        common = dict(rate=0.3, force_reserve_digit=True)
        out_r0 = backend.compress(self._TEXT, digit_neighbor_radius=0, **common)
        out_r3 = backend.compress(self._TEXT, digit_neighbor_radius=3, **common)
        # Radius>0 protects surrounding words too, so it never keeps *fewer*
        # tokens than radius=0 for the same input/rate.
        assert len(out_r3.split()) >= len(out_r0.split())