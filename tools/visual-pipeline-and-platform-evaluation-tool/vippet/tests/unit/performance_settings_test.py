# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for performance-benchmark settings resolution."""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.performance.perf_helpers import settings as s


def _flatten(data: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for name, value in data.items():
        if isinstance(value, dict):
            keys |= _flatten(value, f"{prefix}{name}.")
        else:
            keys.add(f"{prefix}{name}")
    return keys


class _TmpConfigMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def write_config(self, text: str, name: str = "cfg.yaml") -> Path:
        path = Path(self._tmp.name) / name
        path.write_text(text, encoding="utf-8")
        return path


class TestSpecsCoverage(unittest.TestCase):
    def test_every_yaml_key_has_a_spec_and_flag(self) -> None:
        import yaml

        spec_keys = set(s.SPECS_BY_KEY)
        for preset in sorted(s.CONFIG_DIR.glob("*.yaml")):
            with self.subTest(preset=preset.name):
                data = yaml.safe_load(preset.read_text(encoding="utf-8"))
                self.assertLessEqual(_flatten(data), spec_keys)

    def test_flags_are_unique(self) -> None:
        flags = [spec.flag for spec in s.SPECS] + [
            spec.negative_flag for spec in s.SPECS if spec.negative_flag
        ]
        self.assertEqual(len(flags), len(set(flags)))

    def test_all_presets_resolve(self) -> None:
        for preset in ("default", "quick", "full"):
            with self.subTest(preset=preset):
                resolved = s.resolve_settings(preset, env={})
                self.assertEqual(set(resolved.values), set(s.SPECS_BY_KEY))


class TestPrecedence(_TmpConfigMixin):
    def test_default_then_yaml_then_env_then_cli(self) -> None:
        path = self.write_config(
            'vippet:\n  base_url: "http://yaml:1/api"\n'
            "metrics:\n  sample_interval_seconds: 3\n"
        )
        env = {"VIPPET_BASE_URL": "http://env:2/api", "PERF_METRICS_INTERVAL": "4"}

        only_yaml = s.resolve_settings(path, env={})
        self.assertEqual(only_yaml["vippet.base_url"], "http://yaml:1/api")
        self.assertEqual(only_yaml.sources["vippet.base_url"], s.SOURCE_YAML)
        self.assertEqual(only_yaml["vippet.timeout"], 600.0)
        self.assertEqual(only_yaml.sources["vippet.timeout"], s.SOURCE_DEFAULT)

        with_env = s.resolve_settings(path, env=env)
        self.assertEqual(with_env["vippet.base_url"], "http://env:2/api")
        self.assertEqual(with_env["metrics.sample_interval_seconds"], 4.0)

        with_cli = s.resolve_settings(
            path, env=env, cli_overrides={"vippet.base_url": "http://cli:3/api"}
        )
        self.assertEqual(with_cli["vippet.base_url"], "http://cli:3/api")
        self.assertEqual(with_cli.sources["vippet.base_url"], s.SOURCE_CLI)

    def test_job_env_vars_shared_with_functional_helpers(self) -> None:
        # Direct pytest and the CLI must see the same values as helpers.config.
        path = self.write_config(
            "vippet:\n  poll_interval: 3\n  max_job_duration: 300\n"
        )
        from_yaml = s.resolve_settings(path, env={})
        self.assertEqual(from_yaml["vippet.poll_interval"], 3.0)
        self.assertEqual(from_yaml["vippet.max_job_duration"], 300)
        from_env = s.resolve_settings(
            path,
            env={"VIPPET_JOB_POLL_INTERVAL": "1.5", "VIPPET_JOB_TIMEOUT_SECONDS": "90"},
        )
        self.assertEqual(from_env["vippet.poll_interval"], 1.5)
        self.assertEqual(from_env["vippet.max_job_duration"], 90)
        self.assertEqual(from_env.sources["vippet.max_job_duration"], s.SOURCE_ENV)

    def test_empty_env_value_is_ignored(self) -> None:
        path = self.write_config('results:\n  output_dir: "/yaml"\n')
        resolved = s.resolve_settings(path, env={"PERF_RESULTS_DIR": ""})
        self.assertEqual(resolved["results.output_dir"], "/yaml")

    def test_none_cli_override_is_ignored(self) -> None:
        resolved = s.resolve_settings(
            "quick", env={}, cli_overrides={"benchmark.stream_counts": None}
        )
        self.assertEqual(resolved["benchmark.stream_counts"], [1])

    def test_config_source_selection(self) -> None:
        explicit = self.write_config("{}\n", "explicit.yaml")
        from_file = self.write_config("{}\n", "file.yaml")
        env = {s.ENV_CONFIG_FILE: str(from_file), s.ENV_CONFIG: "quick"}
        self.assertEqual(s.select_config_source(explicit, env), explicit)
        self.assertEqual(s.select_config_source(None, env), from_file)
        self.assertEqual(
            s.select_config_source(None, {s.ENV_CONFIG: "quick"}),
            s.CONFIG_DIR / "quick.yaml",
        )
        self.assertEqual(
            s.select_config_source(None, {}), s.CONFIG_DIR / "default.yaml"
        )

    def test_round_trip_through_yaml(self) -> None:
        resolved = s.resolve_settings(
            "full", env={}, cli_overrides={"benchmark.pipelines": ["a", "b"]}
        )
        path = self.write_config(resolved.to_yaml())
        again = s.resolve_settings(path, env={})
        self.assertEqual(dict(again.values), dict(resolved.values))


class TestValidation(_TmpConfigMixin):
    def test_missing_preset_fails_loudly(self) -> None:
        with self.assertRaisesRegex(s.SettingsError, "unknown config preset"):
            s.resolve_settings("does-not-exist", env={})

    def test_missing_path_fails_loudly(self) -> None:
        with self.assertRaisesRegex(s.SettingsError, "not found"):
            s.resolve_settings(Path(self._tmp.name) / "nope.yaml", env={})

    def test_unknown_yaml_key_rejected(self) -> None:
        path = self.write_config("vippet:\n  base_ulr: x\n")
        with self.assertRaisesRegex(s.SettingsError, "unknown key"):
            s.resolve_settings(path, env={})

    def test_invalid_env_value_names_the_source(self) -> None:
        with self.assertRaisesRegex(s.SettingsError, "env VIPPET_BASE_URL"):
            s.resolve_settings(env={"VIPPET_BASE_URL": "ftp://host"})

    def test_coercions(self) -> None:
        spec = s.SPECS_BY_KEY
        self.assertEqual(spec["benchmark.stream_counts"].coerce("1, 3,3"), [1, 3])
        self.assertEqual(spec["benchmark.pipelines"].coerce("*"), "*")
        self.assertEqual(spec["benchmark.pipelines"].coerce("a,b"), ["a", "b"])
        self.assertEqual(spec["benchmark.filters.skip_pipelines"].coerce(""), [])
        self.assertIs(spec["results.create_latest_link"].coerce("false"), False)
        bad = [
            ("benchmark.stream_counts", "0"),
            ("benchmark.stream_counts", []),
            ("benchmark.pipelines", "*,a"),
            ("vippet.timeout", "0"),
            ("benchmark.execution.max_retries", "-1"),
            ("benchmark.execution.max_retries", True),
            ("benchmark.execution.output_mode", "stdout"),
            ("results.formats", "json,xml"),
            ("vippet.base_url", "localhost/api"),
            ("vippet.timeout", "nan"),
            ("vippet.timeout", "inf"),
            ("vippet.timeout", float("nan")),
            ("vippet.poll_interval", "-inf"),
            ("benchmark.execution.retry_delay_seconds", "nan"),
            ("vippet.max_job_duration", "1.5"),
            ("vippet.max_job_duration", float("inf")),
            ("benchmark.stream_counts", "1,nan"),
        ]
        for key, value in bad:
            with self.subTest(key=key, value=value):
                with self.assertRaises(s.SettingsError):
                    spec[key].coerce(value)


if __name__ == "__main__":
    unittest.main()
