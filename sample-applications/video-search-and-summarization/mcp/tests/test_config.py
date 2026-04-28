# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for runtime configuration parsing."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from src.core.config import (
    get_settings,
    _read_api_base_url,
    _read_bool,
    _read_filter_config_path,
    _read_path,
    _read_port,
    _read_positive_float,
    _read_spec_url,
)


class SpecUrlTests(unittest.TestCase):
    """Tests for _read_spec_url()."""

    def test_read_spec_url_requires_explicit_runtime_spec_url(self) -> None:
        """Spec URL must be set via API_SPEC_URL environment variable."""
        original_spec_url = os.environ.pop("API_SPEC_URL", None)
        try:
            with self.assertRaisesRegex(ValueError, "Set API_SPEC_URL"):
                _read_spec_url()
        finally:
            if original_spec_url is not None:
                os.environ["API_SPEC_URL"] = original_spec_url

    def test_read_spec_url_strips_whitespace(self) -> None:
        """Spec URL should have surrounding whitespace stripped."""
        original_spec_url = os.environ.get("API_SPEC_URL")
        try:
            os.environ["API_SPEC_URL"] = "  http://example.com/api.json  "
            self.assertEqual(_read_spec_url(), "http://example.com/api.json")
        finally:
            if original_spec_url is not None:
                os.environ["API_SPEC_URL"] = original_spec_url
            else:
                os.environ.pop("API_SPEC_URL", None)


class ApiBaseUrlTests(unittest.TestCase):
    """Tests for _read_api_base_url()."""

    def test_read_api_base_url_requires_explicit_url(self) -> None:
        """API base URL must be set via API_BASE_URL environment variable."""
        original_base_url = os.environ.pop("API_BASE_URL", None)
        try:
            with self.assertRaisesRegex(ValueError, "Set API_BASE_URL"):
                _read_api_base_url()
        finally:
            if original_base_url is not None:
                os.environ["API_BASE_URL"] = original_base_url

    def test_read_api_base_url_strips_trailing_slash(self) -> None:
        """API base URL should have trailing slash removed."""
        original_base_url = os.environ.get("API_BASE_URL")
        try:
            os.environ["API_BASE_URL"] = "http://example.com/api/"
            self.assertEqual(_read_api_base_url(), "http://example.com/api")
        finally:
            if original_base_url is not None:
                os.environ["API_BASE_URL"] = original_base_url
            else:
                os.environ.pop("API_BASE_URL", None)


class FilterConfigPathTests(unittest.TestCase):
    """Tests for _read_filter_config_path()."""

    def test_read_filter_config_path_requires_env_var(self) -> None:
        """Filter config path must be set via FILTER_FILE_PATH environment variable."""
        original_path = os.environ.pop("FILTER_FILE_PATH", None)
        try:
            with self.assertRaisesRegex(ValueError, "Set FILTER_FILE_PATH"):
                _read_filter_config_path()
        finally:
            if original_path is not None:
                os.environ["FILTER_FILE_PATH"] = original_path

    def test_read_filter_config_path_validates_file_exists(self) -> None:
        """Filter config path must exist on the filesystem."""
        original_path = os.environ.get("FILTER_FILE_PATH")
        try:
            os.environ["FILTER_FILE_PATH"] = "/nonexistent/path/to/filter.json"
            with self.assertRaisesRegex(ValueError, "does not exist"):
                _read_filter_config_path()
        finally:
            if original_path is not None:
                os.environ["FILTER_FILE_PATH"] = original_path
            else:
                os.environ.pop("FILTER_FILE_PATH", None)

    def test_read_filter_config_path_accepts_existing_file(self) -> None:
        """Filter config path should return the path if the file exists."""
        original_path = os.environ.get("FILTER_FILE_PATH")
        try:
            with TemporaryDirectory() as temp_dir:
                filter_file = Path(temp_dir) / "search.json"
                filter_file.write_text("{}", encoding="utf-8")
                os.environ["FILTER_FILE_PATH"] = str(filter_file)

                result = _read_filter_config_path()
                self.assertEqual(result, str(filter_file))
        finally:
            if original_path is not None:
                os.environ["FILTER_FILE_PATH"] = original_path
            else:
                os.environ.pop("FILTER_FILE_PATH", None)


class PositiveFloatTests(unittest.TestCase):
    """Tests for _read_positive_float()."""

    def test_read_positive_float_returns_default_when_unset(self) -> None:
        """Should return the default value when environment variable is unset."""
        os.environ.pop("TEST_FLOAT", None)
        self.assertEqual(_read_positive_float("TEST_FLOAT", 42.0), 42.0)

    def test_read_positive_float_parses_valid_value(self) -> None:
        """Should parse and return a valid positive float."""
        os.environ["TEST_FLOAT"] = "3.14"
        try:
            self.assertAlmostEqual(_read_positive_float("TEST_FLOAT", 0.0), 3.14)
        finally:
            os.environ.pop("TEST_FLOAT", None)

    def test_read_positive_float_rejects_zero(self) -> None:
        """Should reject zero (must be strictly positive)."""
        os.environ["TEST_FLOAT"] = "0"
        try:
            with self.assertRaisesRegex(ValueError, "must be greater than zero"):
                _read_positive_float("TEST_FLOAT", 0.0)
        finally:
            os.environ.pop("TEST_FLOAT", None)

    def test_read_positive_float_rejects_negative(self) -> None:
        """Should reject negative values."""
        os.environ["TEST_FLOAT"] = "-5.5"
        try:
            with self.assertRaisesRegex(ValueError, "must be greater than zero"):
                _read_positive_float("TEST_FLOAT", 0.0)
        finally:
            os.environ.pop("TEST_FLOAT", None)

    def test_read_positive_float_rejects_non_number(self) -> None:
        """Should reject non-numeric values."""
        os.environ["TEST_FLOAT"] = "not-a-number"
        try:
            with self.assertRaisesRegex(ValueError, "must be a valid number"):
                _read_positive_float("TEST_FLOAT", 0.0)
        finally:
            os.environ.pop("TEST_FLOAT", None)


class PortTests(unittest.TestCase):
    """Tests for _read_port()."""

    def test_read_port_returns_default_when_unset(self) -> None:
        """Should return the default value when environment variable is unset."""
        os.environ.pop("TEST_PORT", None)
        self.assertEqual(_read_port("TEST_PORT", 8000), 8000)

    def test_read_port_parses_valid_value(self) -> None:
        """Should parse and return a valid port number."""
        os.environ["TEST_PORT"] = "9999"
        try:
            self.assertEqual(_read_port("TEST_PORT", 0), 9999)
        finally:
            os.environ.pop("TEST_PORT", None)

    def test_read_port_rejects_zero(self) -> None:
        """Should reject port 0 (must be in range [1, 65535])."""
        os.environ["TEST_PORT"] = "0"
        try:
            with self.assertRaisesRegex(ValueError, "must be between 1 and 65535"):
                _read_port("TEST_PORT", 0)
        finally:
            os.environ.pop("TEST_PORT", None)

    def test_read_port_rejects_too_high(self) -> None:
        """Should reject port numbers > 65535."""
        os.environ["TEST_PORT"] = "99999"
        try:
            with self.assertRaisesRegex(ValueError, "must be between 1 and 65535"):
                _read_port("TEST_PORT", 0)
        finally:
            os.environ.pop("TEST_PORT", None)

    def test_read_port_rejects_non_integer(self) -> None:
        """Should reject non-integer values."""
        os.environ["TEST_PORT"] = "abc"
        try:
            with self.assertRaisesRegex(ValueError, "must be a valid integer port"):
                _read_port("TEST_PORT", 0)
        finally:
            os.environ.pop("TEST_PORT", None)


class BoolTests(unittest.TestCase):
    """Tests for _read_bool()."""

    def test_read_bool_returns_default_when_unset(self) -> None:
        """Should return the default value when environment variable is unset."""
        os.environ.pop("TEST_BOOL", None)
        self.assertTrue(_read_bool("TEST_BOOL", True))
        self.assertFalse(_read_bool("TEST_BOOL", False))

    def test_read_bool_parses_true_forms(self) -> None:
        """Should recognize true/yes/on/1 (case-insensitive)."""
        for true_form in ["true", "TRUE", "yes", "YES", "on", "ON", "1"]:
            os.environ["TEST_BOOL"] = true_form
            self.assertTrue(_read_bool("TEST_BOOL", False))
            os.environ.pop("TEST_BOOL")

    def test_read_bool_parses_false_forms(self) -> None:
        """Should recognize false/no/off/0 (case-insensitive)."""
        for false_form in ["false", "FALSE", "no", "NO", "off", "OFF", "0"]:
            os.environ["TEST_BOOL"] = false_form
            self.assertFalse(_read_bool("TEST_BOOL", True))
            os.environ.pop("TEST_BOOL")

    def test_read_bool_rejects_invalid_value(self) -> None:
        """Should reject unrecognized values."""
        os.environ["TEST_BOOL"] = "maybe"
        try:
            with self.assertRaisesRegex(ValueError, "must be one of"):
                _read_bool("TEST_BOOL", True)
        finally:
            os.environ.pop("TEST_BOOL", None)


class PathTests(unittest.TestCase):
    """Tests for _read_path()."""

    def test_read_path_returns_default_when_unset(self) -> None:
        """Should return the default value when environment variable is unset."""
        os.environ.pop("TEST_PATH", None)
        self.assertEqual(_read_path("TEST_PATH", "/default"), "/default")

    def test_read_path_ensures_leading_slash(self) -> None:
        """Should add a leading slash if missing."""
        os.environ["TEST_PATH"] = "mcp"
        try:
            self.assertEqual(_read_path("TEST_PATH", "/"), "/mcp")
        finally:
            os.environ.pop("TEST_PATH", None)

    def test_read_path_preserves_leading_slash(self) -> None:
        """Should preserve an existing leading slash."""
        os.environ["TEST_PATH"] = "/mcp"
        try:
            self.assertEqual(_read_path("TEST_PATH", "/"), "/mcp")
        finally:
            os.environ.pop("TEST_PATH", None)

    def test_read_path_uses_default_for_blank_input(self) -> None:
        """Should use the default value if the environment variable is blank."""
        os.environ["TEST_PATH"] = "   "
        try:
            self.assertEqual(_read_path("TEST_PATH", "/default"), "/default")
        finally:
            os.environ.pop("TEST_PATH", None)


class SettingsTests(unittest.TestCase):
    """Tests for get_settings() environment integration."""

    def setUp(self) -> None:
        get_settings.cache_clear()

    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_get_settings_reads_required_and_optional_environment(self) -> None:
        """Should build Settings from current environment variables."""
        with TemporaryDirectory() as temp_dir:
            filter_file = Path(temp_dir) / "search.json"
            filter_file.write_text("{}", encoding="utf-8")

            env = {
                "API_SPEC_URL": " http://vss.example/manager/swagger/json ",
                "API_BASE_URL": " http://vss.example/manager/ ",
                "FILTER_FILE_PATH": str(filter_file),
                "REQUEST_TIMEOUT": "12.5",
                "LOG_LEVEL": "debug",
                "MCP_HOST": "0.0.0.0",
                "MCP_PORT": "9000",
                "MCP_PATH": "mcp",
                "MCP_STATELESS_HTTP": "false",
            }

            with patch.dict(os.environ, env, clear=True):
                settings = get_settings()

        self.assertEqual(settings.spec_url, "http://vss.example/manager/swagger/json")
        self.assertEqual(settings.api_base_url, "http://vss.example/manager")
        self.assertEqual(settings.filter_config_path, str(filter_file))
        self.assertEqual(settings.request_timeout_seconds, 12.5)
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.mcp_host, "0.0.0.0")
        self.assertEqual(settings.mcp_port, 9000)
        self.assertEqual(settings.mcp_path, "/mcp")
        self.assertFalse(settings.stateless_http)

    def test_get_settings_requires_filter_file_to_exist(self) -> None:
        """Should fail early when the configured filter file does not exist."""
        env = {
            "API_SPEC_URL": "http://vss.example/spec.json",
            "API_BASE_URL": "http://vss.example/api",
            "FILTER_FILE_PATH": "/missing/filter.json",
        }

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "does not exist"):
                get_settings()


if __name__ == "__main__":
    unittest.main()
