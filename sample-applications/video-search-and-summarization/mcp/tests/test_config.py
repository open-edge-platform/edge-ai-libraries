from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

from src.config import _read_spec_url, _resolve_path_input


class ConfigPathTests(unittest.TestCase):
    def test_resolve_path_input_prefers_current_working_directory(self) -> None:
        original_cwd = Path.cwd()
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_file = temp_path / "demo-filter.json"
            config_file.write_text("{}", encoding="utf-8")

            os.chdir(temp_path)
            try:
                resolved = _resolve_path_input("demo-filter.json")
            finally:
                os.chdir(original_cwd)

        self.assertEqual(resolved, str(config_file.resolve()))

    def test_resolve_path_input_returns_default_for_blank_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            default_path = Path(temp_dir) / "default-filter.json"

            resolved = _resolve_path_input("   ", default_path=default_path)

        self.assertEqual(resolved, str(default_path))

    def test_read_spec_url_requires_explicit_runtime_spec_url(self) -> None:
        original_spec_url = os.environ.pop("APP_PROXY_SPEC_URL", None)
        try:
            with self.assertRaisesRegex(ValueError, "Set APP_PROXY_SPEC_URL"):
                _read_spec_url()
        finally:
            if original_spec_url is not None:
                os.environ["APP_PROXY_SPEC_URL"] = original_spec_url


if __name__ == "__main__":
    unittest.main()
