# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for override_credentials: Base64 decoding, grouped-key validation, and unknown key rejection."""

import base64
import os
import pytest

from src.api.models import _decode_override_credentials
from src.plugins.geti_plugin import GetiPlugin
from src.plugins.external_sources_plugin import ExternalSourcesPlugin
from src.plugins.huggingface_plugin import HuggingFacePlugin


# --- Base64 decoding tests ---


class TestDecodeOverrideCredentials:
    def test_none_returns_none(self):
        assert _decode_override_credentials(None) is None

    def test_valid_base64_decoded(self):
        token = "my-secret-token"
        encoded = base64.b64encode(token.encode()).decode()
        result = _decode_override_credentials({"HF_TOKEN": encoded})
        assert result == {"HF_TOKEN": "my-secret-token"}

    def test_multiple_keys_decoded(self):
        host = base64.b64encode(b"https://geti.example.com").decode()
        assert _decode_override_credentials({"GETI_HOST": host}) == {
            "GETI_HOST": "https://geti.example.com",
        }

    def test_null_value_preserved(self):
        result = _decode_override_credentials({"HF_TOKEN": None})
        assert result == {"HF_TOKEN": None}

    def test_invalid_base64_rejected(self):
        with pytest.raises(ValueError, match="must be a valid Base64-encoded"):
            _decode_override_credentials({"HF_TOKEN": "not!!valid!!base64"})

    def test_non_utf8_base64_rejected(self):
        # Valid Base64 but decodes to non-UTF-8 bytes
        non_utf8 = base64.b64encode(b"\xff\xfe").decode()
        with pytest.raises(ValueError, match="must be a valid Base64-encoded"):
            _decode_override_credentials({"KEY": non_utf8})

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError, match="must be an object"):
            _decode_override_credentials("not-a-dict")

    def test_non_string_value_rejected(self):
        with pytest.raises(ValueError, match="must be a Base64-encoded string"):
            _decode_override_credentials({"KEY": 12345})


# --- Grouped-key validation tests (Geti plugin) ---


class TestGetiGroupedKeyValidation:
    @pytest.fixture
    def plugin(self, monkeypatch):
        monkeypatch.setenv("GETI_HOST", "https://env-host.com")
        return GetiPlugin()

    def test_geti_host_override_resolves(self, plugin):
        result = plugin.resolve_config({"GETI_HOST": "https://override-host.com"})
        assert result["GETI_HOST"] == "https://override-host.com"

    def test_host_override_without_token_is_allowed(self, plugin):
        """Geti 3.0 permits local deployments without a token."""
        result = plugin.resolve_config({
            "GETI_HOST": "https://local-host.com",
        })
        assert result == {"GETI_HOST": "https://local-host.com"}

    def test_no_override_uses_env(self, plugin):
        result = plugin.resolve_config({})
        assert result["GETI_HOST"] == "https://env-host.com"


# --- Unknown key rejection tests ---


class TestUnknownKeyRejection:
    def test_geti_rejects_unknown_key(self):
        plugin = GetiPlugin()
        with pytest.raises(ValueError, match="Unknown override key.*INVALID_KEY"):
            plugin.resolve_config({"INVALID_KEY": "value"})

    def test_huggingface_rejects_unknown_key(self):
        plugin = HuggingFacePlugin()
        with pytest.raises(ValueError, match="Unknown override key.*BAD_KEY"):
            plugin.resolve_config({"BAD_KEY": "value"})

    def test_external_sources_rejects_unknown_key(self):
        plugin = ExternalSourcesPlugin()
        with pytest.raises(ValueError, match="Unknown override key.*FAKE"):
            plugin.resolve_config({"FAKE": "value"})


# --- remote-url allowlist override ---


class TestRemoteUrlAllowlistOverride:
    def test_allowlist_override_replaces_env(self, monkeypatch):
        monkeypatch.setenv("EXTERNAL_SOURCES_URL_ALLOWLIST", "old.com/path")
        plugin = ExternalSourcesPlugin()
        result = plugin.resolve_config({
            "EXTERNAL_SOURCES_URL_ALLOWLIST": "new.com/models,other.com/data"
        })
        assert result["EXTERNAL_SOURCES_URL_ALLOWLIST"] == "new.com/models,other.com/data"
