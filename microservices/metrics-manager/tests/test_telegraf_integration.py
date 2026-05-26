# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Wiring tests for Telegraf configuration mounting and custom-metrics.

These tests parse the actual config files shipped with the image (telegraf.conf,
compose.yaml, supervisord.conf, Dockerfile) and assert that the mount points,
override mechanisms and ordering guarantees are wired up correctly. They do not
require a running Docker daemon - any regression in the wiring (e.g. someone
breaks the TELEGRAF_CONFIG override path, drops the custom-metrics volume or
removes the Prometheus output the SSE stream depends on) will fail in CI.

End-to-end Docker-based tests are documented at the bottom of this file.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TELEGRAF_CONF = REPO_ROOT / "telegraf.conf"
COMPOSE_YAML = REPO_ROOT / "compose.yaml"
SUPERVISORD_CONF = REPO_ROOT / "supervisord.conf"
DOCKERFILE = REPO_ROOT / "Dockerfile"
ENTRYPOINT = REPO_ROOT / "entrypoint.sh"


@pytest.fixture(scope="module")
def telegraf_text() -> str:
    return TELEGRAF_CONF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_text() -> str:
    return COMPOSE_YAML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def supervisord_text() -> str:
    return SUPERVISORD_CONF.read_text(encoding="utf-8")


class TestDefaultTelegrafConfig:
    """Default telegraf.conf must declare the inputs/outputs the service relies on."""

    def test_no_websocket_output(self, telegraf_text: str):
        # The service streams metrics to clients via SSE (/metrics/stream),
        # which scrapes the Prometheus endpoint below. The legacy
        # [[outputs.websocket]] relay to /ws/collector has been removed - guard
        # against accidental re-introduction (Telegraf would log endless
        # "connection refused" errors against a non-existent endpoint).
        assert "[[outputs.websocket]]" not in telegraf_text
        assert "/ws/collector" not in telegraf_text

    def test_prometheus_output_enabled(self, telegraf_text: str):
        assert "[[outputs.prometheus_client]]" in telegraf_text
        assert ':9273"' in telegraf_text

    def test_http_listener_for_custom_metrics_relay(self, telegraf_text: str):
        # /api/v1/metrics endpoints persist via Telegraf's HTTP listener on :8186.
        assert "[[inputs.http_listener_v2]]" in telegraf_text
        assert ':8186"' in telegraf_text

    def test_custom_metrics_directory_input(self, telegraf_text: str):
        # The default config must execute user scripts dropped into /app/custom-metrics.
        assert "/app/custom-metrics" in telegraf_text
        assert "[[inputs.exec]]" in telegraf_text

    def test_hostname_override_wired_in_agent(self, telegraf_text: str):
        # METRICS_MANAGER_HOSTNAME must reach Telegraf's [agent] block so the
        # built-in inputs (cpu/mem/temp) carry the same `host=` tag as the
        # custom readers (qmassa_reader.py, npu_reader.py).
        assert 'hostname = "${METRICS_MANAGER_HOSTNAME}"' in telegraf_text


class TestHostnameOverrideWiring:
    """METRICS_MANAGER_HOSTNAME must be wired through compose + both readers."""

    def test_compose_passes_env_var(self, compose_text: str):
        assert "METRICS_MANAGER_HOSTNAME=${METRICS_MANAGER_HOSTNAME:-}" in compose_text

    def test_qmassa_reader_reads_env_var(self):
        text = (REPO_ROOT / "scripts" / "qmassa_reader.py").read_text(encoding="utf-8")
        assert 'os.environ.get("METRICS_MANAGER_HOSTNAME")' in text
        assert "or os.uname()[1]" in text

    def test_npu_reader_reads_env_var(self):
        text = (REPO_ROOT / "scripts" / "npu_reader.py").read_text(encoding="utf-8")
        assert 'os.environ.get("METRICS_MANAGER_HOSTNAME")' in text
        assert "or os.uname()[1]" in text


class TestComposeWiring:
    """compose.yaml must expose the override knobs and mount points users rely on."""

    def test_telegraf_config_override_env_var(self, compose_text: str):
        # Users override the default config by setting TELEGRAF_CONFIG=./my.conf.
        assert "TELEGRAF_CONFIG" in compose_text
        assert "/etc/telegraf/telegraf.conf" in compose_text

    def test_telegraf_d_directory_mount(self, compose_text: str):
        # Drop-in directory for additional .conf files.
        assert "/etc/telegraf/telegraf.d" in compose_text

    def test_custom_metrics_volume_mounted(self, compose_text: str):
        assert "/app/custom-metrics" in compose_text
        assert "custom-metrics:" in compose_text

    def test_telegraf_ports_exposed(self, compose_text: str):
        assert "9273" in compose_text  # Prometheus
        assert "8186" in compose_text  # HTTP listener
        assert "9090" in compose_text  # API + SSE


class TestSupervisordOrdering:
    """Telegraf must come up before metrics-manager so the API has a Prometheus
    endpoint to scrape (for SSE) and an HTTP listener to push custom metrics to
    as soon as it starts serving requests."""

    def test_telegraf_priority_lower_than_metrics_manager(self, supervisord_text: str):
        # Lower priority => earlier start in supervisord. metrics-manager depends
        # on Telegraf at runtime (scrapes :9273, pushes to :8186), so Telegraf
        # must start first.
        ms_section = supervisord_text.split("[program:metrics-manager]", 1)[1].split(
            "[program:", 1
        )[0]
        tg_section = supervisord_text.split("[program:telegraf]", 1)[1].split(
            "[program:", 1
        )[0]

        def _priority(section: str) -> int:
            for line in section.splitlines():
                if line.strip().startswith("priority="):
                    return int(line.split("=", 1)[1].strip())
            raise AssertionError("priority= missing from supervisord program section")

        assert _priority(tg_section) < _priority(ms_section)


class TestImageDirectories:
    """Dockerfile/entrypoint must create the directories that Telegraf reads from."""

    def test_dockerfile_creates_custom_metrics_dir(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        assert "/app/custom-metrics" in text

    def test_entrypoint_creates_custom_metrics_dir(self):
        text = ENTRYPOINT.read_text(encoding="utf-8")
        assert "/app/custom-metrics" in text

    def test_no_dead_collector_signals_references(self):
        # Legacy directory removed during OEP cleanup - regressions would
        # silently re-introduce an unused mount.
        for path in (DOCKERFILE, ENTRYPOINT):
            text = path.read_text(encoding="utf-8")
            assert "collector-signals" not in text, (
                f"{path.name} still references the removed collector-signals directory"
            )


# -----------------------------------------------------------------------------
# Manual end-to-end test commands (require a running Docker daemon)
# -----------------------------------------------------------------------------
"""
1. Start the full stack:
   docker compose up -d

2. Verify Telegraf is publishing system metrics:
   curl http://localhost:9273/metrics | grep cpu_usage

3. Test custom script execution:
   docker exec metrics-manager sh -c 'cat > /app/custom-metrics/test.sh <<EOF
   #!/bin/sh
   echo "test_metric value=123"
   EOF
   chmod +x /app/custom-metrics/test.sh'
   # Wait ~10s for the exec input interval, then:
   curl http://localhost:9273/metrics | grep test_metric

4. Test custom telegraf.conf override:
   TELEGRAF_CONFIG=./my-telegraf.conf docker compose up -d

5. Confirm the SSE stream is delivering metrics:
   curl -N -H 'Accept: text/event-stream' http://localhost:9090/metrics/stream

6. Verify NPU reader (on NPU-equipped hosts only):
   docker exec metrics-manager ps -ef | grep npu_reader
   curl -s http://localhost:9273/metrics | grep '^npu_'
"""
