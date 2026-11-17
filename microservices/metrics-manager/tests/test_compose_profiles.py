# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import configparser
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from docker_collectors import ConfigurationError, validate_environment

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def services():
    return yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]


def test_exactly_two_runtime_variants(services):
    assert set(services) == {"metrics-manager", "metrics-manager-host-nic", "metrics-manager-test"}
    bridge = services["metrics-manager"]
    host = services["metrics-manager-host-nic"]
    assert "profiles" not in bridge
    assert "network_mode" not in bridge
    assert bridge["networks"] == ["metric-network"]
    assert host["profiles"] == ["host-nic-telemetry"]
    assert host["network_mode"] == "host"
    assert "ports" not in host
    assert "networks" not in host
    assert "depends_on" not in host
    assert services["metrics-manager-test"]["profiles"] == ["test"]


def test_variants_share_image_collectors_and_access(services):
    bridge = services["metrics-manager"]
    host = services["metrics-manager-host-nic"]
    for key in (
        "image",
        "build",
        "user",
        "privileged",
        "group_add",
        "security_opt",
        "devices",
        "volumes",
        "pid",
        "restart",
        "healthcheck",
    ):
        assert bridge[key] == host[key]
    expected_differences = {
        "METRICS_PORT",
        "TELEGRAF_PORT",
        "TELEGRAF_HTTP_PORT",
        "TELEGRAF_HTTP_ENDPOINT",
        "PROMETHEUS_TELEGRAF_ENDPOINT",
        "ENABLE_NETWORK",
    }
    assert bridge["environment"].keys() == host["environment"].keys()
    assert {
        key for key, value in bridge["environment"].items() if value != host["environment"][key]
    } == expected_differences
    assert bridge["container_name"] != host["container_name"]


def test_network_defaults_and_explicit_false(services):
    assert services["metrics-manager"]["environment"]["ENABLE_NETWORK"] == "${ENABLE_NETWORK-false}"
    assert (
        services["metrics-manager-host-nic"]["environment"]["ENABLE_NETWORK"]
        == "${ENABLE_NETWORK-true}"
    )
    # Copying the reference env must not inadvertently override the host default.
    lines = (ROOT / ".env.example").read_text().splitlines()
    assert "#ENABLE_NETWORK=false" in lines
    assert not any(line.startswith("ENABLE_NETWORK=") for line in lines)


def test_ports_and_internal_urls_are_consistent(services):
    bridge = services["metrics-manager"]
    host = services["metrics-manager-host-nic"]
    for key, default in (
        ("METRICS_PORT", "9090"),
        ("TELEGRAF_PORT", "9273"),
        ("TELEGRAF_HTTP_PORT", "8186"),
    ):
        assert bridge["environment"][key] == default
        assert host["environment"][key] == "${HOST_" + key + "-" + default + "}"
        assert "${HOST_" + key + ":-" + default + "}:" + default in bridge["ports"]
    for environment in (bridge["environment"], host["environment"]):
        assert (
            environment["TELEGRAF_HTTP_ENDPOINT"]
            == "http://localhost:" + environment["TELEGRAF_HTTP_PORT"] + "/write"
        )
        assert (
            environment["PROMETHEUS_TELEGRAF_ENDPOINT"]
            == "http://localhost:" + environment["TELEGRAF_PORT"]
        )
    config = tomllib.loads((ROOT / "telegraf.conf").read_text())
    assert config["outputs"]["prometheus_client"][0]["listen"] == ":${TELEGRAF_PORT}"
    assert config["inputs"]["http_listener_v2"][0]["service_address"] == ":${TELEGRAF_HTTP_PORT}"


@pytest.mark.parametrize("key", ["METRICS_PORT", "TELEGRAF_PORT", "TELEGRAF_HTTP_PORT"])
@pytest.mark.parametrize("value", ["", "0", "65536", "-1", "9x", "9090/path", " 9090"])
def test_invalid_listener_ports_fail_visibly(key, value):
    with pytest.raises(ConfigurationError, match=key):
        validate_environment({key: value})


def test_duplicate_listener_ports_rejected():
    with pytest.raises(ConfigurationError, match="must be distinct"):
        validate_environment({"TELEGRAF_PORT": "9090"})


def test_custom_port_boundaries_allowed():
    validate_environment(
        {"METRICS_PORT": "1", "TELEGRAF_PORT": "65535", "TELEGRAF_HTTP_PORT": "8187"}
    )


def test_healthcheck_and_uvicorn_use_runtime_port(services, tmp_path):
    health = services["metrics-manager-host-nic"]["healthcheck"]["test"]
    assert health[:3] == ["CMD", "python", "-c"]
    (tmp_path / "sitecustomize.py").write_text(
        "import urllib.request\n"
        "def verify(url, timeout):\n"
        "    assert url == 'http://localhost:19090/health', url\n"
        "urllib.request.urlopen = verify\n"
    )
    subprocess.run(
        [sys.executable, "-c", health[3]],
        env={**os.environ, "METRICS_PORT": "19090", "PYTHONPATH": str(tmp_path)},
        check=True,
    )
    supervisor = configparser.ConfigParser(interpolation=None)
    supervisor.read(ROOT / "supervisord.conf")
    assert "--port %(ENV_METRICS_PORT)s" in supervisor["program:metrics-manager"]["command"]
    dockerfile = (ROOT / "Dockerfile").read_text()
    healthcheck = dockerfile.split("HEALTHCHECK", 1)[1]
    assert "os.environ['METRICS_PORT']" in healthcheck
    assert "localhost:9090" not in healthcheck
