# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Single source of truth for performance-benchmark settings.

Effective settings are composed in this order (later wins)::

    built-in defaults -> YAML config file -> environment variables -> CLI flags

Every configurable key is declared once in :data:`SPECS`. The pytest
``conftest`` (through :mod:`perf_helpers.config`) and the CLI
(:mod:`perf_helpers.cli`) both resolve settings through
:func:`resolve_settings`, so the two entry points cannot drift apart.

This module has no import-time side effects and does not touch the network.
"""

import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

PERF_DIR: Path = Path(__file__).resolve().parents[1]
CONFIG_DIR: Path = PERF_DIR / "config"
DEFAULT_PRESET: str = "default"

# Env vars that select the YAML source. PERF_CONFIG_FILE (an explicit path,
# written by the CLI for its pytest subprocess) wins over PERF_CONFIG (a
# preset name or a path).
ENV_CONFIG_FILE: str = "PERF_CONFIG_FILE"
ENV_CONFIG: str = "PERF_CONFIG"

_PRESET_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

OUTPUT_MODES: tuple[str, ...] = ("disabled", "file", "live_stream")
RESULT_FORMAT_CHOICES: tuple[str, ...] = ("json", "csv")

SOURCE_DEFAULT = "default"
SOURCE_YAML = "yaml"
SOURCE_ENV = "env"
SOURCE_CLI = "cli"


class SettingsError(ValueError):
    """Raised when a config file or a setting value is invalid."""


# --------------------------------------------------------------------------- #
# Value coercion / validation
# --------------------------------------------------------------------------- #


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return _split_csv(value)
    if isinstance(value, (list, tuple)):
        items: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise SettingsError(
                    f"expected a list of non-empty strings, got {value!r}"
                )
            items.append(item.strip())
        return items
    raise SettingsError(f"expected a list or comma-separated string, got {value!r}")


def _as_number(value: Any, cast: Callable[[Any], Any]) -> Any:
    if isinstance(value, bool):
        raise SettingsError(f"expected a number, got {value!r}")
    if isinstance(value, (int, float)):
        number = cast(value)
    elif isinstance(value, str):
        try:
            number = cast(value.strip())
        except (ValueError, OverflowError) as exc:
            raise SettingsError(f"expected a number, got {value!r}") from exc
    else:
        raise SettingsError(f"expected a number, got {value!r}")
    # NaN compares false against every bound, so it would slip past
    # _check_min; infinities make timeouts/intervals meaningless.
    if not math.isfinite(number):
        raise SettingsError(f"expected a finite number, got {value!r}")
    return number


def _as_int(value: Any) -> int:
    if isinstance(value, float) and not value.is_integer():
        raise SettingsError(f"expected an integer, got {value!r}")
    return _as_number(value, int)


def _check_min(value: float, minimum: float | None, exclusive: bool) -> None:
    if minimum is None:
        return
    if exclusive and value <= minimum:
        raise SettingsError(f"must be greater than {minimum:g}, got {value!r}")
    if not exclusive and value < minimum:
        raise SettingsError(f"must be at least {minimum:g}, got {value!r}")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise SettingsError(f"expected a boolean, got {value!r}")


def _as_url(value: Any) -> str:
    if not isinstance(value, str):
        raise SettingsError(f"expected a URL string, got {value!r}")
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SettingsError(f"expected an http(s) URL with a host, got {value!r}")
    return url


def _as_path_str(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"expected a non-empty path, got {value!r}")
    return value.strip()


def _as_pipelines(value: Any) -> str | list[str]:
    if isinstance(value, str) and value.strip() == "*":
        return "*"
    items = _as_str_list(value)
    if not items:
        raise SettingsError("expected '*' or at least one pipeline id")
    if "*" in items:
        raise SettingsError("'*' cannot be combined with explicit pipeline ids")
    return items


@dataclass(frozen=True)
class SettingSpec:
    """Declaration of one configurable key."""

    key: str
    """Dotted path inside the YAML file, e.g. ``vippet.base_url``."""
    flag: str
    """Long CLI flag, e.g. ``--base-url``."""
    kind: str
    """One of: str, url, int, float, bool, str_list, int_list, pipelines, choice, choice_list."""
    default: Any
    help: str
    env: str | None = None
    minimum: float | None = None
    exclusive_min: bool = False
    choices: tuple[str, ...] = field(default_factory=tuple)
    negative_flag: str | None = None
    """For booleans: the flag that sets the value to False."""
    metavar: str | None = None

    @property
    def dest(self) -> str:
        return self.key.replace(".", "__")

    def coerce(self, value: Any) -> Any:
        """Convert *value* (from YAML, env or CLI) to the canonical type."""
        kind = self.kind
        if kind == "str":
            return _as_path_str(value)
        if kind == "url":
            return _as_url(value)
        if kind == "bool":
            return _as_bool(value)
        if kind in {"int", "float"}:
            number = _as_int(value) if kind == "int" else _as_number(value, float)
            _check_min(number, self.minimum, self.exclusive_min)
            return number
        if kind == "pipelines":
            return _as_pipelines(value)
        if kind == "str_list":
            return _as_str_list(value)
        if kind == "int_list":
            raw = _as_str_list(value) if isinstance(value, str) else value
            if not isinstance(raw, (list, tuple)) or not raw:
                raise SettingsError(
                    f"expected a non-empty list of integers, got {value!r}"
                )
            numbers: list[int] = []
            for item in raw:
                number = _as_int(item)
                _check_min(number, self.minimum, self.exclusive_min)
                if number not in numbers:
                    numbers.append(number)
            return numbers
        if kind == "choice":
            if not isinstance(value, str) or value.strip() not in self.choices:
                raise SettingsError(
                    f"expected one of {list(self.choices)}, got {value!r}"
                )
            return value.strip()
        if kind == "choice_list":
            items = _as_str_list(value)
            if not items:
                raise SettingsError(f"expected at least one of {list(self.choices)}")
            invalid = [item for item in items if item not in self.choices]
            if invalid:
                raise SettingsError(
                    f"unsupported value(s) {invalid}; expected any of {list(self.choices)}"
                )
            return items
        raise AssertionError(f"unknown setting kind {kind!r}")  # pragma: no cover


# Keep this table in sync with config/*.yaml. A unit test asserts every YAML
# key has a spec (and therefore a CLI flag).
SPECS: tuple[SettingSpec, ...] = (
    # --- vippet ---
    SettingSpec(
        "vippet.base_url",
        "--base-url",
        "url",
        "http://localhost/api/v1",
        "ViPPET API base URL.",
        env="VIPPET_BASE_URL",
        metavar="URL",
    ),
    SettingSpec(
        "vippet.timeout",
        "--timeout",
        "float",
        600.0,
        "HTTP request timeout in seconds.",
        minimum=0,
        exclusive_min=True,
        metavar="SECONDS",
    ),
    SettingSpec(
        "vippet.readiness_timeout_seconds",
        "--readiness-timeout",
        "float",
        60.0,
        "Maximum time to wait for ViPPET readiness before discovery.",
        minimum=0,
        exclusive_min=True,
        metavar="SECONDS",
    ),
    SettingSpec(
        "vippet.poll_interval",
        "--poll-interval",
        "float",
        2.0,
        "Job status polling interval in seconds.",
        # Shared with the functional-test helpers (helpers.config).
        env="VIPPET_JOB_POLL_INTERVAL",
        minimum=0,
        exclusive_min=True,
        metavar="SECONDS",
    ),
    SettingSpec(
        "vippet.max_job_duration",
        "--max-job-duration",
        # int: helpers.config parses VIPPET_JOB_TIMEOUT_SECONDS with int().
        "int",
        600,
        "Maximum time to wait for a job to complete, in whole seconds.",
        env="VIPPET_JOB_TIMEOUT_SECONDS",
        minimum=1,
        metavar="SECONDS",
    ),
    # --- benchmark ---
    SettingSpec(
        "benchmark.pipelines",
        "--pipelines",
        "pipelines",
        "*",
        "'*' or comma-separated pipeline ids to benchmark.",
        metavar="IDS",
    ),
    SettingSpec(
        "benchmark.variants",
        "--variants",
        "str_list",
        ["cpu", "gpu", "npu"],
        "Comma-separated allowed device families; a variant runs only if "
        "every family it uses is listed (e.g. gpu_npu needs gpu and npu).",
        metavar="FAMILIES",
    ),
    SettingSpec(
        "benchmark.stream_counts",
        "--streams",
        "int_list",
        [1, 3],
        "Comma-separated stream counts, e.g. 1,3,5.",
        minimum=1,
        metavar="COUNTS",
    ),
    SettingSpec(
        "benchmark.execution.max_retries",
        "--max-retries",
        "int",
        2,
        "Retries for a job that does not reach COMPLETED.",
        minimum=0,
        metavar="N",
    ),
    SettingSpec(
        "benchmark.execution.retry_delay_seconds",
        "--retry-delay",
        "float",
        5.0,
        "Delay between retries in seconds.",
        minimum=0,
        metavar="SECONDS",
    ),
    SettingSpec(
        "benchmark.execution.output_mode",
        "--output-mode",
        "choice",
        "disabled",
        "Pipeline output mode.",
        choices=OUTPUT_MODES,
    ),
    SettingSpec(
        "benchmark.execution.max_runtime",
        "--max-runtime",
        "float",
        0.0,
        "Seconds each pipeline run lasts (0 = until end of video).",
        minimum=0,
        metavar="SECONDS",
    ),
    SettingSpec(
        "benchmark.filters.skip_pipelines",
        "--skip-pipelines",
        "str_list",
        [],
        "Comma-separated pipeline ids to skip ('' for none).",
        metavar="IDS",
    ),
    SettingSpec(
        "benchmark.filters.skip_variants",
        "--skip-variants",
        "str_list",
        [],
        "Comma-separated variant names to skip, e.g. GPU_NPU ('' for none).",
        metavar="VARIANTS",
    ),
    SettingSpec(
        "benchmark.filters.require_models",
        "--require-models",
        "bool",
        True,
        "Require all pipeline models to be installed. Accepted; the "
        "run-time behaviour of --no-require-models is pending.",
        negative_flag="--no-require-models",
    ),
    # --- metrics ---
    SettingSpec(
        "metrics.metrics_url",
        "--metrics-url",
        "url",
        "http://localhost/metrics/stream",
        "Hardware metrics endpoint.",
        env="VIPPET_METRICS_URL",
        metavar="URL",
    ),
    SettingSpec(
        "metrics.sample_interval_seconds",
        "--metrics-interval",
        "float",
        2.0,
        "Hardware metrics sampling interval in seconds.",
        env="PERF_METRICS_INTERVAL",
        minimum=0,
        exclusive_min=True,
        metavar="SECONDS",
    ),
    # --- results ---
    SettingSpec(
        "results.output_dir",
        "--results-dir",
        "str",
        str(PERF_DIR / "results"),
        "Output directory for benchmark reports.",
        env="PERF_RESULTS_DIR",
        metavar="DIR",
    ),
    SettingSpec(
        "results.formats",
        "--formats",
        "choice_list",
        ["json", "csv"],
        "Comma-separated export formats.",
        choices=RESULT_FORMAT_CHOICES,
        metavar="FORMATS",
    ),
    SettingSpec(
        "results.create_latest_link",
        "--latest-link",
        "bool",
        True,
        "Create/update the 'latest' symlink in the results directory.",
        negative_flag="--no-latest-link",
    ),
)

SPECS_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SPECS}


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ResolvedSettings:
    """Effective settings plus where each value came from."""

    values: Mapping[str, Any]
    sources: Mapping[str, str]
    config_path: Path

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def to_nested(self) -> dict[str, Any]:
        """Return values as a nested dict with the YAML file layout."""
        nested: dict[str, Any] = {}
        for key, value in self.values.items():
            node = nested
            *parents, leaf = key.split(".")
            for part in parents:
                node = node.setdefault(part, {})
            node[leaf] = value
        return nested

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_nested(), sort_keys=False)


def resolve_config_path(config: str | os.PathLike[str]) -> Path:
    """Map a preset name (``quick``) or a file path to an existing YAML path."""
    text = os.fspath(config).strip()
    if not text:
        raise SettingsError("config name/path must not be empty")
    if _PRESET_NAME_RE.match(text) and not Path(text).is_file():
        path = CONFIG_DIR / f"{text}.yaml"
        if not path.is_file():
            presets = sorted(p.stem for p in CONFIG_DIR.glob("*.yaml"))
            raise SettingsError(
                f"unknown config preset {text!r}; available presets: {presets}"
            )
        return path
    path = Path(text).expanduser()
    if not path.is_file():
        raise SettingsError(f"config file not found: {path}")
    return path


def select_config_source(
    config: str | os.PathLike[str] | None, env: Mapping[str, str]
) -> Path:
    """Pick the YAML file: explicit arg > PERF_CONFIG_FILE > PERF_CONFIG > default."""
    if config is not None:
        return resolve_config_path(config)
    if env.get(ENV_CONFIG_FILE):
        return resolve_config_path(env[ENV_CONFIG_FILE])
    return resolve_config_path(env.get(ENV_CONFIG) or DEFAULT_PRESET)


def _flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for name, value in data.items():
        key = f"{prefix}{name}"
        if isinstance(value, Mapping):
            flat.update(_flatten(value, f"{key}."))
        else:
            flat[key] = value
    return flat


def load_yaml_values(path: Path) -> dict[str, Any]:
    """Load *path* and return its values keyed by dotted setting key.

    Unknown keys are rejected so typos fail loudly instead of being ignored.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        raise SettingsError(f"cannot read config {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise SettingsError(f"config {path} must be a mapping at the top level")
    flat = _flatten(data)
    unknown = sorted(set(flat) - set(SPECS_BY_KEY))
    if unknown:
        raise SettingsError(f"config {path} has unknown key(s): {unknown}")
    return flat


def resolve_settings(
    config: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> ResolvedSettings:
    """Compose defaults -> YAML -> env -> CLI and validate every value.

    ``cli_overrides`` is keyed by dotted setting key; ``None`` values are
    treated as "not given".
    """
    env = os.environ if env is None else env
    cli_overrides = cli_overrides or {}

    config_path = select_config_source(config, env)
    yaml_values = load_yaml_values(config_path)

    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for spec in SPECS:
        layers: list[tuple[str, Any]] = [(SOURCE_DEFAULT, spec.default)]
        if spec.key in yaml_values:
            layers.append((SOURCE_YAML, yaml_values[spec.key]))
        if spec.env and env.get(spec.env):
            layers.append((SOURCE_ENV, env[spec.env]))
        if cli_overrides.get(spec.key) is not None:
            layers.append((SOURCE_CLI, cli_overrides[spec.key]))

        source, raw = layers[-1]
        try:
            values[spec.key] = spec.coerce(raw)
        except SettingsError as exc:
            origin = {
                SOURCE_DEFAULT: "built-in default",
                SOURCE_YAML: str(config_path),
                SOURCE_ENV: f"env {spec.env}",
                SOURCE_CLI: spec.flag,
            }[source]
            raise SettingsError(f"invalid {spec.key} from {origin}: {exc}") from exc
        sources[spec.key] = source

    return ResolvedSettings(values=values, sources=sources, config_path=config_path)
