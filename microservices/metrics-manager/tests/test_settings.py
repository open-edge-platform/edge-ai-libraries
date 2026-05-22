# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/settings.py."""

import pytest

from app.settings import Settings


class TestCorsOriginsParsing:
    def test_cors_origins_wildcard_default(self):
        s = Settings(cors_origins_raw="*")
        assert s.cors_origins == ["*"]

    def test_cors_origins_empty_string_returns_wildcard(self):
        """Line 75: empty value falls back to ['*']."""
        s = Settings(cors_origins_raw="")
        assert s.cors_origins == ["*"]

    def test_cors_origins_whitespace_only_returns_wildcard(self):
        """Line 75: whitespace-only value falls back to ['*']."""
        s = Settings(cors_origins_raw="   ")
        assert s.cors_origins == ["*"]

    def test_cors_origins_json_array(self):
        """Lines 78-80: valid JSON array is parsed directly."""
        s = Settings(cors_origins_raw='["http://localhost:3000", "http://example.com"]')
        assert s.cors_origins == ["http://localhost:3000", "http://example.com"]

    def test_cors_origins_invalid_json_falls_back_to_split(self):
        """Lines 78-82: invalid JSON starting with '[' falls back to comma split."""
        s = Settings(cors_origins_raw="[invalid json")
        assert "[invalid json" in s.cors_origins

    def test_cors_origins_comma_separated(self):
        s = Settings(cors_origins_raw="http://a.com,http://b.com")
        assert s.cors_origins == ["http://a.com", "http://b.com"]


class TestLogLevelValidator:
    def test_normalize_log_level_uppercase(self):
        s = Settings(log_level="debug")
        assert s.log_level == "DEBUG"

    def test_normalize_log_level_already_upper(self):
        s = Settings(log_level="INFO")
        assert s.log_level == "INFO"

    def test_normalize_log_level_non_string_passthrough(self):
        """Line 133: non-string value returned as-is."""
        result = Settings.normalize_log_level(42)
        assert result == 42


class TestEnvironmentProperties:
    def test_is_development_true(self):
        s = Settings(environment="development")
        assert s.is_development is True
        assert s.is_production is False

    def test_is_production_true(self):
        """Line 143: is_production property."""
        s = Settings(environment="production")
        assert s.is_production is True
        assert s.is_development is False

    def test_staging_is_neither(self):
        s = Settings(environment="staging")
        assert s.is_development is False
        assert s.is_production is False
