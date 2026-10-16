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

    def test_presets_do_not_override_output_dir(self) -> None:
        for preset in ("default", "quick", "full"):
            with self.subTest(preset=preset):
                resolved = s.resolve_settings(preset, env={})
                self.assertEqual(
                    resolved.sources["results.output_dir"], s.SOURCE_DEFAULT
                )

    def test_default_output_dir_is_absolute(self) -> None:
        resolved = s.resolve_settings("default", env={})
        self.assertEqual(Path(resolved["results.output_dir"]), s.PERF_DIR / "results")

    def test_absolute_output_dir_overrides_are_unaffected(self) -> None:
        resolved = s.resolve_settings(
            "default", env={}, cli_overrides={"results.output_dir": "/abs/path"}
        )
        self.assertEqual(resolved["results.output_dir"], "/abs/path")

    def test_relative_output_dir_override_resolves_against_cwd(self) -> None:
        resolved = s.resolve_settings(
            "default", env={}, cli_overrides={"results.output_dir": "./my-results"}
        )
        self.assertEqual(resolved["results.output_dir"], "./my-results")

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


class TestDeriveMetricsDefaultsFromBaseUrl(unittest.TestCase):
    """Unit tests for the private derivation helper.

    Calling the private function directly (rather than only through
    ``resolve_settings``) lets each case isolate exactly which of
    metrics.metrics_url / metrics.capabilities_url is still at its
    built-in default vs. explicitly set, independent of YAML/env/CLI
    plumbing (covered separately in TestMetricsDerivationIntegration).
    """

    _DEFAULT_METRICS_URL = "http://localhost/metrics/stream"
    _DEFAULT_CAPABILITIES_URL = "http://localhost:9090/api/v1/capabilities"

    def _derive(
        self,
        base_url: str,
        *,
        metrics_source: str = s.SOURCE_DEFAULT,
        metrics_value: str | None = None,
        capabilities_source: str = s.SOURCE_DEFAULT,
        capabilities_value: str | None = None,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            "vippet.base_url": base_url,
            "metrics.metrics_url": metrics_value or self._DEFAULT_METRICS_URL,
            "metrics.capabilities_url": (
                capabilities_value or self._DEFAULT_CAPABILITIES_URL
            ),
        }
        sources = {
            "metrics.metrics_url": metrics_source,
            "metrics.capabilities_url": capabilities_source,
        }
        s._derive_metrics_defaults_from_base_url(values, sources, Path("cfg.yaml"))
        return values

    def test_derives_both_urls_from_default_base_url(self) -> None:
        values = self._derive("http://localhost/api/v1")
        self.assertEqual(values["metrics.metrics_url"], self._DEFAULT_METRICS_URL)
        self.assertEqual(
            values["metrics.capabilities_url"], self._DEFAULT_CAPABILITIES_URL
        )

    def test_derives_from_custom_host(self) -> None:
        values = self._derive("http://board/api/v1")
        self.assertEqual(values["metrics.metrics_url"], "http://board/metrics/stream")
        self.assertEqual(
            values["metrics.capabilities_url"],
            "http://board:9090/api/v1/capabilities",
        )

    def test_metrics_url_keeps_port_capabilities_url_overrides_it(self) -> None:
        # metrics_url reuses the full netloc (host:port); capabilities_url
        # always targets the metrics-manager's own port 9090 regardless of
        # what port base_url uses.
        values = self._derive("http://board:8080/api/v1")
        self.assertEqual(
            values["metrics.metrics_url"], "http://board:8080/metrics/stream"
        )
        self.assertEqual(
            values["metrics.capabilities_url"],
            "http://board:9090/api/v1/capabilities",
        )

    def test_preserves_https_scheme(self) -> None:
        values = self._derive("https://board/api/v1")
        self.assertEqual(values["metrics.metrics_url"], "https://board/metrics/stream")
        self.assertEqual(
            values["metrics.capabilities_url"],
            "https://board:9090/api/v1/capabilities",
        )

    def test_explicit_metrics_url_is_not_overridden(self) -> None:
        values = self._derive(
            "http://board/api/v1",
            metrics_source=s.SOURCE_YAML,
            metrics_value="http://other-host/metrics/stream",
        )
        self.assertEqual(
            values["metrics.metrics_url"], "http://other-host/metrics/stream"
        )
        # capabilities_url has no explicit source, so it is still derived.
        self.assertEqual(
            values["metrics.capabilities_url"],
            "http://board:9090/api/v1/capabilities",
        )

    def test_explicit_capabilities_url_is_not_overridden(self) -> None:
        values = self._derive(
            "http://board/api/v1",
            capabilities_source=s.SOURCE_ENV,
            capabilities_value="http://other-host:1234/api/v1/capabilities",
        )
        self.assertEqual(
            values["metrics.capabilities_url"],
            "http://other-host:1234/api/v1/capabilities",
        )
        self.assertEqual(values["metrics.metrics_url"], "http://board/metrics/stream")

    def test_both_explicit_overrides_are_preserved(self) -> None:
        values = self._derive(
            "http://board/api/v1",
            metrics_source=s.SOURCE_CLI,
            metrics_value="http://m/metrics/stream",
            capabilities_source=s.SOURCE_CLI,
            capabilities_value="http://c:7/api/v1/capabilities",
        )
        self.assertEqual(values["metrics.metrics_url"], "http://m/metrics/stream")
        self.assertEqual(
            values["metrics.capabilities_url"], "http://c:7/api/v1/capabilities"
        )

    def test_raises_when_base_url_has_no_host(self) -> None:
        # "http://:8080/..." passes _as_url (netloc=":8080" is non-empty)
        # but urlparse(...).hostname is None, so derivation must fail loudly
        # instead of silently producing a broken metrics/capabilities URL.
        values = {
            "vippet.base_url": "http://:8080/api/v1",
            "metrics.metrics_url": self._DEFAULT_METRICS_URL,
            "metrics.capabilities_url": self._DEFAULT_CAPABILITIES_URL,
        }
        sources = {
            "metrics.metrics_url": s.SOURCE_DEFAULT,
            "metrics.capabilities_url": s.SOURCE_DEFAULT,
        }
        with self.assertRaisesRegex(s.SettingsError, "missing a host"):
            s._derive_metrics_defaults_from_base_url(values, sources, Path("cfg.yaml"))


class TestMetricsDerivationIntegration(_TmpConfigMixin):
    """End-to-end checks that resolve_settings() actually wires the
    derivation helper up to real YAML/env-resolved values."""

    def test_yaml_base_url_cascades_to_metrics_defaults(self) -> None:
        path = self.write_config('vippet:\n  base_url: "http://board/api/v1"\n')
        resolved = s.resolve_settings(path, env={})
        self.assertEqual(resolved["metrics.metrics_url"], "http://board/metrics/stream")
        self.assertEqual(
            resolved["metrics.capabilities_url"],
            "http://board:9090/api/v1/capabilities",
        )

    def test_env_base_url_cascades_to_metrics_defaults(self) -> None:
        resolved = s.resolve_settings(
            "default", env={"VIPPET_BASE_URL": "http://board:8080/api/v1"}
        )
        self.assertEqual(
            resolved["metrics.metrics_url"], "http://board:8080/metrics/stream"
        )
        self.assertEqual(
            resolved["metrics.capabilities_url"],
            "http://board:9090/api/v1/capabilities",
        )

    def test_explicit_metrics_env_vars_override_derivation(self) -> None:
        resolved = s.resolve_settings(
            "default",
            env={
                "VIPPET_BASE_URL": "http://board/api/v1",
                "VIPPET_METRICS_URL": "http://metrics-host/metrics/stream",
                "VIPPET_CAPABILITIES_URL": "http://caps-host:7/api/v1/capabilities",
            },
        )
        self.assertEqual(
            resolved["metrics.metrics_url"], "http://metrics-host/metrics/stream"
        )
        self.assertEqual(
            resolved["metrics.capabilities_url"],
            "http://caps-host:7/api/v1/capabilities",
        )
        self.assertEqual(resolved.sources["metrics.metrics_url"], s.SOURCE_ENV)
        self.assertEqual(resolved.sources["metrics.capabilities_url"], s.SOURCE_ENV)


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
