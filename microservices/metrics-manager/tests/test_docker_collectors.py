# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import configparser
import os
import subprocess
from pathlib import Path

import pytest
import yaml

import docker_collectors as collectors

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    main = tmp_path / "telegraf.conf"
    main.write_bytes((ROOT / "telegraf.conf").read_bytes())
    dropins = tmp_path / "dropins"
    dropins.mkdir()
    monkeypatch.setattr(collectors.tempfile, "tempdir", str(tmp_path))
    return main, dropins, ROOT / "native/packaging/etc"


@pytest.mark.parametrize("option", collectors.OPTIONS)
@pytest.mark.parametrize("value", ["auto", "TRUE", "1", "", "false ", "yes"])
def test_flags_reject_invalid_values(option, value):
    with pytest.raises(collectors.ConfigurationError, match=f"ENABLE_{option}"):
        collectors.validate_environment({f"ENABLE_{option}": value})


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "5s", "", "9223372037", "9" * 100])
def test_invalid_interval_even_when_disabled(value):
    with pytest.raises(collectors.ConfigurationError, match="TURBOSTAT_INTERVAL"):
        collectors.validate_environment({"TURBOSTAT_INTERVAL": value})


@pytest.mark.parametrize("value", ["turbostat", "/tmp/a b", "$(command)", ""])
def test_invalid_binary_path(value):
    with pytest.raises(collectors.ConfigurationError, match="TURBOSTAT_BIN"):
        collectors.validate_environment({"TURBOSTAT_BIN": value})


def test_defaults_preserve_base_and_add_nothing(configuration):
    main, dropins, examples = configuration
    original = main.read_bytes()
    active = collectors.prepare_config(main, dropins, examples, {})
    assert list(active.iterdir()) == []
    assert main.read_bytes() == original
    assert list(dropins.iterdir()) == []
    assert active.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("option", collectors.OPTIONS)
def test_each_optional_collector_can_be_enabled(configuration, monkeypatch, option):
    monkeypatch.setattr(collectors, "turbostat_available", lambda binary: True)
    active = collectors.prepare_config(*configuration, {f"ENABLE_{option}": "true"})
    assert [file.name for file in active.iterdir()] == [
        f"managed-{option.lower().replace('_', '-')}.conf"
    ]


def test_all_options_keep_baseline_disjoint(configuration, monkeypatch):
    monkeypatch.setattr(collectors, "turbostat_available", lambda binary: True)
    environment = {f"ENABLE_{option}": "true" for option in collectors.OPTIONS}
    active = collectors.prepare_config(*configuration, environment)
    assert len(list(active.glob("*.conf"))) == len(collectors.OPTIONS)
    assert (
        'command = ["/usr/libexec/metrics-manager/mm-plugin-rapl"]'
        in (active / "managed-rapl.conf").read_text()
    )
    extra = collectors.parse_config(
        (active / "managed-powerstat-extra.conf").read_text(), "extra", {}
    )
    assert extra["inputs"]["intel_powerstat"][0]["package_metrics"] == []


def test_custom_config_snapshot_is_preserved_and_not_reused(configuration):
    main, dropins, examples = configuration
    nested = dropins / "local"
    nested.mkdir()
    custom = nested / "sensors.conf"
    custom.write_text('[[inputs.net]]\n interfaces = ["enp1s0"]\n')
    (dropins / "ignored.conf.example").write_text("not active TOML")
    first = collectors.prepare_config(main, dropins, examples, {"ENABLE_RAPL": "true"})
    second = collectors.prepare_config(main, dropins, examples, {"ENABLE_RAPL": "false"})
    assert first != second
    assert (first / "managed-rapl.conf").exists()
    assert not (second / "managed-rapl.conf").exists()
    assert (second / "user-0.conf").read_bytes() == custom.read_bytes()
    assert sorted(path.name for path in dropins.iterdir()) == ["ignored.conf.example", "local"]


@pytest.mark.parametrize("option", collectors.OPTIONS)
@pytest.mark.parametrize("location", ["main", "dropin"])
def test_existing_input_does_not_get_duplicate(configuration, monkeypatch, option, location):
    main, dropins, examples = configuration
    monkeypatch.setattr(collectors, "turbostat_available", lambda binary: True)
    name = option.lower().replace("_", "-")
    text = (
        collectors.RAPL_CONFIG
        if option == "RAPL"
        else (examples / f"telegraf-{name}.conf.example").read_text()
    )
    if location == "main":
        main.write_text(main.read_text() + "\n" + text)
    else:
        (dropins / "custom.conf").write_text(text)
    with pytest.raises(collectors.ConfigurationError, match=f"ENABLE_{option} conflicts"):
        collectors.prepare_config(main, dropins, examples, {f"ENABLE_{option}": "true"})
    # False controls automatic additions, not intentional custom configuration.
    collectors.prepare_config(main, dropins, examples, {f"ENABLE_{option}": "false"})


def test_custom_selection_and_privacy_opt_in_are_preserved(configuration):
    main, dropins, examples = configuration
    selections = {
        "network.conf": '[[inputs.net]]\ninterfaces = ["bond0", "wlan0"]\n',
        "storage.conf": (
            '[[inputs.disk]]\nmount_points = ["/data"]\n'
            '[[inputs.diskio]]\ndevices = ["dm-0", "md0"]\n'
            'skip_serial_number = false\ndevice_tags = ["ID_SERIAL_SHORT"]\n'
        ),
        "irq.conf": '[[inputs.interrupts]]\nfieldinclude = ["total"]\n',
    }
    for name, text in selections.items():
        (dropins / name).write_text(text)
    active = collectors.prepare_config(main, dropins, examples, {})
    assert {path.read_text() for path in active.iterdir()} == set(selections.values())
    for name, text in selections.items():
        assert (dropins / name).read_text() == text


def test_virtual_traffic_cannot_overlap_a_custom_primary_input(configuration):
    main, dropins, examples = configuration
    (dropins / "network.conf").write_text("[[inputs.net]]\ninterfaces = []\n")
    with pytest.raises(collectors.ConfigurationError, match="ENABLE_NETWORK_VIRTUAL conflicts"):
        collectors.prepare_config(main, dropins, examples, {"ENABLE_NETWORK_VIRTUAL": "true"})


def test_partial_storage_overlap_is_explicit_error(configuration):
    main, dropins, examples = configuration
    (dropins / "disk.conf").write_text("[[inputs.disk]]\n")
    with pytest.raises(collectors.ConfigurationError, match="ENABLE_STORAGE conflicts"):
        collectors.prepare_config(main, dropins, examples, {"ENABLE_STORAGE": "true"})


def test_config_errors_are_visible_and_do_not_expose_values(configuration):
    main, dropins, examples = configuration
    main.write_text("private_value = invalid-internal-detail\n")
    with pytest.raises(collectors.ConfigurationError, match="Cannot parse") as error:
        collectors.prepare_config(main, dropins, examples, {})
    assert "invalid-internal-detail" not in str(error.value)
    main.unlink()
    with pytest.raises(FileNotFoundError):
        collectors.prepare_config(main, dropins, examples, {})


@pytest.mark.parametrize("variable", ["${HOST_LABEL}", "$HOST_LABEL"])
def test_telegraf_environment_expansion(variable):
    parsed = collectors.parse_config(
        '[agent]\ninterval = "${INTERVAL}"\nhostname = "' + variable + '"',
        "custom",
        {"INTERVAL": "2s", "HOST_LABEL": 'quoted "label" with \\ backslash'},
    )
    assert parsed["agent"] == {
        "interval": "2s",
        "hostname": 'quoted "label" with \\ backslash',
    }


@pytest.mark.parametrize("variable", ["${RAPL_BIN}", "$RAPL_BIN"])
def test_environment_expanded_native_command_cannot_be_duplicated(configuration, variable):
    main, dropins, examples = configuration
    (dropins / "rapl.conf").write_text('[[inputs.execd]]\ncommand = ["' + variable + '"]\n')
    with pytest.raises(collectors.ConfigurationError, match="ENABLE_RAPL conflicts"):
        collectors.prepare_config(
            main,
            dropins,
            examples,
            {"ENABLE_RAPL": "true", "RAPL_BIN": "/usr/libexec/metrics-manager/mm-plugin-rapl"},
        )


def test_non_string_substitution_is_rejected_like_telegraf_strict_mode():
    with pytest.raises(collectors.ConfigurationError, match="Cannot parse"):
        collectors.parse_config("[agent]\nmetric_batch_size = ${BATCH}", "custom", {"BATCH": "100"})


@pytest.mark.parametrize("text", ['inputs = "invalid"', "[inputs.net]", "[[inputs]]"])
def test_invalid_input_structure_reports_configuration_error(text):
    with pytest.raises(collectors.ConfigurationError, match="Expected"):
        collectors.parse_config(text, "custom.conf", {})


def test_unreadable_dropin_directory_is_not_silently_skipped(configuration, monkeypatch):
    def unreadable_walk(self, *, on_error):
        on_error(PermissionError("Cannot read selected directory"))
        return iter(())

    monkeypatch.setattr(Path, "walk", unreadable_walk)
    with pytest.raises(PermissionError, match="Cannot read selected"):
        collectors.prepare_config(*configuration, {})


def test_empty_hardware_flag_is_invalid():
    with pytest.raises(collectors.ConfigurationError, match="HARDWARE_TELEMETRY_ENABLED"):
        collectors.validate_environment({"HARDWARE_TELEMETRY_ENABLED": ""})


def test_missing_turbostat_skips_only_optional_input(configuration, capsys):
    active = collectors.prepare_config(
        *configuration,
        {"ENABLE_TURBOSTAT": "true", "ENABLE_RAPL": "true", "TURBOSTAT_BIN": "/missing/tool"},
    )
    assert [path.name for path in active.iterdir()] == ["managed-rapl.conf"]
    assert "[WARN] Skipping optional Turbostat" in capsys.readouterr().err


@pytest.fixture
def turbostat_files(tmp_path):
    binary = tmp_path / "turbostat"
    binary.write_text('#!/bin/sh\nprintf "turbostat version 2026.01\\n" >&2\n')
    binary.chmod(0o700)
    msr = tmp_path / "msr"
    msr.write_bytes(b"\0" * 24)
    return binary, msr


def test_turbostat_checks_executable_and_msr(turbostat_files):
    binary, msr = turbostat_files
    assert collectors.turbostat_available(str(binary), msr)
    binary.chmod(0o600)
    assert not collectors.turbostat_available(str(binary), msr)


@pytest.mark.parametrize(
    "script",
    [
        "#!/bin/sh\nexit 1\n",
        "#!/bin/sh\nexit 0\n",
        "#!/missing/interpreter\n",
        "#!/bin/sh\nexec sleep 10\n",
    ],
)
def test_turbostat_incompatible_or_hanging_tool_is_skipped(turbostat_files, script, capsys):
    binary, msr = turbostat_files
    binary.write_text(script)
    assert not collectors.turbostat_available(str(binary), msr)
    assert "[WARN]" in capsys.readouterr().err


def test_turbostat_missing_msr_or_permissions(turbostat_files, monkeypatch, capsys):
    binary, msr = turbostat_files
    assert not collectors.turbostat_available(str(binary), msr.with_name("missing"))
    original_open = os.open

    def deny_msr(path, flags, *args, **kwargs):
        if path == msr:
            raise PermissionError("simulated MSR permission denial")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", deny_msr)
    assert not collectors.turbostat_available(str(binary), msr)
    assert "MSR is unavailable or not readable" in capsys.readouterr().err


def test_compose_and_supervisor_wire_options():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    environment = compose["services"]["metrics-manager"]["environment"]
    for option in collectors.OPTIONS:
        assert environment[f"ENABLE_{option}"] == f"${{ENABLE_{option}-false}}"
    assert environment["TURBOSTAT_INTERVAL"] == "${TURBOSTAT_INTERVAL-5}"
    # Do not require an optional host tool to exist for the default deployment.
    assert "HOST_TURBOSTAT_BIN" not in str(compose["services"]["metrics-manager"]["volumes"])
    supervisor = configparser.ConfigParser(interpolation=None)
    supervisor.read(ROOT / "supervisord.conf")
    command = supervisor["program:telegraf"]["command"]
    assert '--config "%(ENV_TELEGRAF_CONFIG_PATH)s"' in command
    assert '--config-directory "%(ENV_TELEGRAF_ACTIVE_CONFIG_DIR)s"' in command
    entrypoint = (ROOT / "entrypoint.sh").read_text()
    assert entrypoint.index("docker_collectors.py") < entrypoint.index("exec supervisord")
    assert "export TELEGRAF_ACTIVE_CONFIG_DIR" in entrypoint


def test_image_ships_helper_and_examples():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert dockerfile.count("COPY docker_collectors.py ./") == 2
    assert (
        "COPY native/packaging/etc/telegraf-*.conf.example "
        "/usr/share/metrics-manager/telegraf-examples/"
    ) in dockerfile


def test_entrypoint_shell_syntax():
    subprocess.run(["bash", "-n", str(ROOT / "entrypoint.sh")], check=True)
