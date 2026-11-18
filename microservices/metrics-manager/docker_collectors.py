# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Select Docker-only Telegraf additions without modifying mounted configuration."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

OPTIONS = (
    "RAPL",
    "POWERSTAT_EXTRA",
    "TURBOSTAT",
    "TEMPERATURE",
    "INTERRUPTS",
    "NETWORK",
    "NETWORK_VIRTUAL",
    "STORAGE",
)
EXAMPLES = Path("/usr/share/metrics-manager/telegraf-examples")
DROPINS = Path("/etc/telegraf/telegraf.d")
RAPL_CONFIG = """# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
[[inputs.execd]]
  command = ["/usr/libexec/metrics-manager/mm-plugin-rapl"]
  signal = "none"
  restart_delay = "10s"
  data_format = "influx"
"""


class ConfigurationError(ValueError):
    """An invalid startup configuration that must not be silently ignored."""


def log(level: str, message: str) -> None:
    print(f"[{level}] {message}", file=sys.stderr)


def validate_environment(environment: Mapping[str, str]) -> dict[str, bool]:
    ports = []
    for key, default in (
        ("METRICS_PORT", "9090"),
        ("TELEGRAF_PORT", "9273"),
        ("TELEGRAF_HTTP_PORT", "8186"),
    ):
        value = environment.get(key, default)
        if not re.fullmatch(r"[1-9][0-9]{0,4}", value) or int(value) > 65535:
            raise ConfigurationError(f"{key} must be an integer between 1 and 65535")
        ports.append(int(value))
    if len(set(ports)) != len(ports):
        raise ConfigurationError("API, Prometheus and HTTP listener ports must be distinct")
    enabled = {}
    for name in (*OPTIONS, "HARDWARE_TELEMETRY_ENABLED"):
        key = name if name == "HARDWARE_TELEMETRY_ENABLED" else f"ENABLE_{name}"
        value = environment.get(key, "true" if name == "HARDWARE_TELEMETRY_ENABLED" else "false")
        if value not in ("true", "false"):
            raise ConfigurationError(f"{key} must be exactly true or false")
        enabled[name] = value == "true"
    interval = environment.get("TURBOSTAT_INTERVAL", "5")
    if not re.fullmatch(r"[1-9][0-9]{0,9}", interval) or int(interval) > 9223372036:
        raise ConfigurationError(
            "TURBOSTAT_INTERVAL must be positive integer seconds fitting a Telegraf duration"
        )
    binary = environment.get("TURBOSTAT_BIN", "/usr/local/bin/turbostat")
    if not re.fullmatch(r"/[a-zA-Z0-9_./+-]+", binary):
        raise ConfigurationError(
            "TURBOSTAT_BIN must be an absolute path without spaces or expansion"
        )
    return enabled


def turbostat_available(binary: str, msr: Path = Path("/dev/cpu/0/msr")) -> bool:
    if not Path(binary).is_file() or not os.access(binary, os.X_OK):
        log("WARN", "Skipping optional Turbostat: mounted executable is unavailable")
        return False
    try:
        # Some versions write --version to stderr. Never echo tool output, which
        # may contain host details; a file also bounds memory use for a broken tool.
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                [binary, "--version"],
                stdout=output,
                stderr=output,
                timeout=3,
                check=False,
            )
            output.seek(0)
            version = output.read(4096).lower()
        if result.returncode != 0 or b"turbostat version" not in version:
            log("WARN", "Skipping optional Turbostat: container --version check failed")
            return False
    except (OSError, subprocess.TimeoutExpired):
        log("WARN", "Skipping optional Turbostat: container --version check failed or timed out")
        return False
    try:
        fd = os.open(msr, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            if len(os.pread(fd, 8, 0x10)) != 8:
                raise OSError("Incomplete MSR read")
        finally:
            os.close(fd)
    except OSError:
        log("WARN", "Skipping optional Turbostat: CPU 0 MSR is unavailable or not readable")
        return False
    return True


def expand_strings(value: Any, environment: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return re.sub(
            r"\$(?:\{([^}]*)\}|([0-9*#$@!?\-])|([A-Za-z_][A-Za-z0-9_]*))",
            lambda match: environment.get(match[1] or match[2] or match[3] or "", ""),
            value,
        )
    if isinstance(value, list):
        return [expand_strings(item, environment) for item in value]
    if isinstance(value, dict):
        return {key: expand_strings(item, environment) for key, item in value.items()}
    return value


def parse_config(text: str, name: str, environment: Mapping[str, str]) -> dict[str, Any]:
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        # TOML exception messages can include raw configuration values.
        raise ConfigurationError(f"Cannot parse Telegraf configuration: {name}") from exc
    inputs = config.get("inputs", {})
    if not isinstance(inputs, dict) or any(
        not isinstance(instances, list) or any(not isinstance(item, dict) for item in instances)
        for instances in inputs.values()
    ):
        raise ConfigurationError(f"Expected [[inputs.plugin]] tables in {name}")
    # Telegraf 1.40 uses strict string-only environment substitution after TOML
    # parsing. Do not interpret quotes in environment values as configuration.
    return {key: expand_strings(value, environment) for key, value in config.items()}


def string_list(config: dict[str, Any], key: str) -> list[str]:
    value = config.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(f"Telegraf input {key} must be an array of strings")
    return value


def walk_error(error: OSError) -> None:
    raise error


def input_conflicts(plugin: str, proposed: dict[str, Any], existing: dict[str, Any]) -> bool:
    if plugin == "execd":
        command = string_list(existing, "command")
        return bool(command) and Path(command[0]).name == "mm-plugin-rapl"
    if plugin == "temp":
        return existing.get("name_override") == proposed.get("name_override")
    if plugin == "intel_powerstat":
        # The baseline package/C-state input and the extra frequency/temperature
        # input are intentionally distinct. Missing lists mean Telegraf defaults.
        return any(
            key not in existing
            or bool(set(string_list(proposed, key)) & set(string_list(existing, key)))
            for key in ("cpu_metrics", "package_metrics")
            if proposed.get(key)
        )
    # Arbitrary interface/device glob intersections cannot be proven disjoint.
    # Leave such custom selections under manual control instead of double sampling.
    return True


def prepare_config(
    main_config: Path,
    dropins: Path,
    examples: Path,
    environment: Mapping[str, str],
) -> Path:
    enabled = validate_environment(environment)
    main = parse_config(main_config.read_text(encoding="utf-8"), str(main_config), environment)
    if not dropins.is_dir():
        raise ConfigurationError(f"Telegraf drop-in directory is missing: {dropins}")

    files: dict[str, str] = {}
    custom = [(str(main_config), main)]
    sources = sorted(
        directory / name
        for directory, _, names in dropins.walk(on_error=walk_error)
        for name in names
        if name.endswith(".conf")
    )
    for index, source in enumerate(sources):
        text = source.read_text(encoding="utf-8")
        custom.append((str(source), parse_config(text, str(source), environment)))
        files[f"user-{index}.conf"] = text

    for option in OPTIONS:
        if not enabled[option]:
            continue
        name = option.lower().replace("_", "-")
        text = (
            RAPL_CONFIG
            if option == "RAPL"
            else (examples / f"telegraf-{name}.conf.example").read_text(encoding="utf-8")
        )
        proposed = parse_config(text, name, environment)
        for source_name, config in custom:
            for plugin, inputs in proposed.get("inputs", {}).items():
                for item in inputs:
                    for existing in config.get("inputs", {}).get(plugin, []):
                        if input_conflicts(plugin, item, existing):
                            raise ConfigurationError(
                                f"ENABLE_{option} conflicts with inputs.{plugin} in {source_name}; "
                                f"set ENABLE_{option}=false to keep the custom input, "
                                "or remove that input from your configuration"
                            )
        if option == "TURBOSTAT" and not turbostat_available(
            environment.get("TURBOSTAT_BIN", "/usr/local/bin/turbostat")
        ):
            continue
        files[f"managed-{name}.conf"] = text
        log("INFO", f"Enabled optional collector: {option}")

    # A private snapshot avoids writing to user mounts and cannot retain a
    # previously enabled collector when the container starts again.
    active = Path(tempfile.mkdtemp(prefix="metrics-manager-telegraf-"))
    try:
        for name, text in files.items():
            (active / name).write_text(text, encoding="utf-8")
    except OSError:
        shutil.rmtree(active)
        raise
    log("INFO", f"Selected {len(files)} Telegraf drop-in files")
    return active


def main() -> int:
    try:
        active = prepare_config(
            Path(os.environ.get("TELEGRAF_CONFIG_PATH", "/etc/telegraf/telegraf.conf")),
            DROPINS,
            EXAMPLES,
            os.environ,
        )
    except (ConfigurationError, OSError) as exc:
        log("ERROR", f"Cannot configure Docker collectors: {exc}")
        return 1
    print(active)
    return 0


if __name__ == "__main__":
    sys.exit(main())
