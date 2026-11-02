"""Tests for harness/profiles.py."""
from __future__ import annotations

import pytest

from adaptive_token_compressor.core.exceptions import ConfigError
from adaptive_token_compressor.harness.normalizer import (
    NullNormalizer,
    WorkspaceNormalizer,
)
from adaptive_token_compressor.harness.profiles import (
    GENERIC_PROFILE,
    OPENCLAW_PROFILE,
    CompressorProfile,
    resolve_profile,
)
from adaptive_token_compressor.harness.sectioning import SectioningConfig


# ─────────────────────────────────────────────────────────────────────────────
# Built-in profiles
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenclawProfile:
    def test_name(self):
        assert OPENCLAW_PROFILE.name == "openclaw"

    def test_has_primary_headings(self):
        assert len(OPENCLAW_PROFILE.sectioning.primary_headings) > 0
        assert "## Tooling" in OPENCLAW_PROFILE.sectioning.primary_headings
        assert "## Subagent Context" in OPENCLAW_PROFILE.sectioning.primary_headings

    def test_has_preserve_headings(self):
        assert len(OPENCLAW_PROFILE.sectioning.preserve_headings) > 0
        assert "## Tooling" in OPENCLAW_PROFILE.sectioning.preserve_headings
        assert "## Subagent Context" in OPENCLAW_PROFILE.sectioning.preserve_headings

    def test_has_workspace_pattern(self):
        assert OPENCLAW_PROFILE.sectioning.workspace_path_pattern is not None
        assert "openclaw" in OPENCLAW_PROFILE.sectioning.workspace_path_pattern
        assert "pinchbench" in OPENCLAW_PROFILE.sectioning.workspace_path_pattern

    def test_uses_workspace_normalizer(self):
        assert isinstance(OPENCLAW_PROFILE.normalizer, WorkspaceNormalizer)


class TestGenericProfile:
    def test_name(self):
        assert GENERIC_PROFILE.name == "generic"

    def test_no_primary_headings(self):
        assert GENERIC_PROFILE.sectioning.primary_headings == []

    def test_no_preserve_headings(self):
        assert GENERIC_PROFILE.sectioning.preserve_headings == set()

    def test_no_workspace_pattern(self):
        assert GENERIC_PROFILE.sectioning.workspace_path_pattern is None

    def test_uses_null_normalizer(self):
        assert isinstance(GENERIC_PROFILE.normalizer, NullNormalizer)


# ─────────────────────────────────────────────────────────────────────────────
# resolve_profile()
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveProfile:
    def test_resolve_openclaw(self):
        profile = resolve_profile("openclaw")
        assert profile is OPENCLAW_PROFILE

    def test_resolve_generic(self):
        profile = resolve_profile("generic")
        assert profile is GENERIC_PROFILE

    def test_unknown_profile_raises_config_error(self):
        with pytest.raises(ConfigError, match="Unknown profile"):
            resolve_profile("nonexistent")

    def test_error_message_lists_available(self):
        with pytest.raises(ConfigError, match="openclaw"):
            resolve_profile("nonexistent")

    def test_case_sensitive(self):
        with pytest.raises(ConfigError):
            resolve_profile("OpenClaw")  # Wrong case


# ─────────────────────────────────────────────────────────────────────────────
# CompressorProfile dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressorProfile:
    def test_frozen(self):
        with pytest.raises(Exception):  # FrozenInstanceError
            OPENCLAW_PROFILE.name = "modified"

    def test_custom_profile_construction(self):
        custom = CompressorProfile(
            name="custom",
            sectioning=SectioningConfig(),
            normalizer=NullNormalizer(),
        )
        assert custom.name == "custom"
