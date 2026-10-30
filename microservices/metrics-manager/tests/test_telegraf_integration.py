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

import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
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
        assert 'listen = ":${TELEGRAF_PORT}"' in telegraf_text

    def test_http_listener_for_custom_metrics_relay(self, telegraf_text: str):
        # /api/v1/metrics endpoints persist via Telegraf's HTTP listener on :8186.
        assert "[[inputs.http_listener_v2]]" in telegraf_text
        assert 'service_address = ":${TELEGRAF_HTTP_PORT}"' in telegraf_text

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
        assert "METRICS_MANAGER_HOSTNAME: ${METRICS_MANAGER_HOSTNAME:-}" in compose_text

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

    def test_default_service_keeps_bridge_network_and_ports(self, compose_text: str):
        # Existing deployments rely on the metric-network bridge, the
        # metrics-manager service name, and configurable host-port mappings.
        # This must be the default (no profile) startup contract.
        default_block = compose_text.split("metrics-manager-host-nic:", 1)[0]
        assert "${HOST_METRICS_PORT:-9090}:9090" in default_block
        assert "${HOST_TELEGRAF_PORT:-9273}:9273" in default_block
        assert "${HOST_TELEGRAF_HTTP_PORT:-8186}:8186" in default_block
        assert "metric-network" in default_block

    def test_host_nic_service_is_opt_in_profile(self, compose_text: str):
        # inputs.net/inputs.ethtool need the host netns to read physical NICs,
        # but that must never be the default startup behavior (see above).
        host_nic_block = compose_text.split("metrics-manager-host-nic:", 1)[1]
        assert "host-nic-telemetry" in host_nic_block
        assert "network_mode: host" in host_nic_block
        # No bridge attachment or Docker port mapping for this variant.
        host_nic_section = host_nic_block.split("metrics-manager-test:", 1)[0]
        assert "\n    ports:" not in host_nic_section
        assert "\n    networks:" not in host_nic_section

    def test_host_nic_service_derives_ports_from_host_vars(self, compose_text: str):
        # Listener ports and connection URLs must track the same HOST_* knobs
        # used for port mapping in the default variant.
        host_nic_section = compose_text.split("metrics-manager-host-nic:", 1)[1].split(
            "metrics-manager-test:", 1
        )[0]
        assert "METRICS_PORT: ${HOST_METRICS_PORT:-9090}" in host_nic_section
        assert "TELEGRAF_PORT: ${HOST_TELEGRAF_PORT:-9273}" in host_nic_section
        assert "TELEGRAF_HTTP_PORT: ${HOST_TELEGRAF_HTTP_PORT:-8186}" in host_nic_section
        assert (
            "PROMETHEUS_TELEGRAF_ENDPOINT: http://localhost:${HOST_TELEGRAF_PORT:-9273}"
            in host_nic_section
        )
        assert (
            "TELEGRAF_HTTP_ENDPOINT: http://localhost:${HOST_TELEGRAF_HTTP_PORT:-8186}/write"
            in host_nic_section
        )

    def test_healthchecks_use_runtime_metrics_port(self, compose_text: str):
        # Both variants must probe the port METRICS_PORT actually resolves to,
        # not a hardcoded 9090 (the host-nic variant may remap it).
        assert compose_text.count("os.environ.get('METRICS_PORT', '9090')") == 2


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


class TestTelegrafConfigDirectoryLoaded:
    """The telegraf.d/ drop-ins are inert unless telegraf is launched with
    --config-directory. Guard the loader flag that makes them take effect."""

    def test_supervisord_passes_config_directory(self, supervisord_text: str):
        assert "--config-directory /etc/telegraf/active.d" in supervisord_text

    def test_dockerfile_copies_dropins(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        assert "COPY telegraf.d/" in text


class TestTcmiCollectorWiring:
    """TCMI hardware-telemetry drop-ins and their execd readers must be shipped
    and gated. Each ENABLE_* toggle decides whether entrypoint.sh loads the
    corresponding telegraf.d/*.conf; the readers idle gracefully when the
    hardware is absent, so gating never breaks a deploy."""

    TELEGRAF_D = REPO_ROOT / "telegraf.d"
    SCRIPTS = REPO_ROOT / "scripts"

    # (basename, ships-active-as-.conf) for the native + execd drop-ins.
    # 60-turbostat and 91-gpu-throttle are opt-in but ship as .conf (gated by
    # ENABLE_TURBOSTAT / ENABLE_GPU_THROTTLE in entrypoint.sh, not by filename).
    ACTIVE_DROPINS = ["10-power", "20-dram-bw", "30-disk", "40-net",
                      "50-interrupts", "60-turbostat", "70-temp-stats",
                      "90-tcmi-execd", "91-gpu-throttle"]

    def test_active_dropins_present(self):
        for base in self.ACTIVE_DROPINS:
            assert (self.TELEGRAF_D / f"{base}.conf").is_file(), f"missing {base}.conf"

    def test_no_conf_example_files_remain(self):
        # All .conf.example files have been converted or removed; none should exist.
        examples = list(self.TELEGRAF_D.glob("*.conf.example"))
        assert examples == [], f"unexpected .conf.example files: {examples}"

    def test_execd_reader_scripts_present(self):
        for script in ("rapl_reader.py", "dram_bw_reader.py", "gpu_throttle_reader.py"):
            assert (self.SCRIPTS / script).is_file(), f"missing scripts/{script}"

    def test_execd_readers_honor_hostname_and_idle(self):
        # Same contract as npu_reader.py: stable host tag + graceful idle.
        for script in ("rapl_reader.py", "dram_bw_reader.py", "gpu_throttle_reader.py"):
            text = (self.SCRIPTS / script).read_text(encoding="utf-8")
            assert 'os.environ.get("METRICS_MANAGER_HOSTNAME")' in text
            assert "or os.uname()[1]" in text
            assert "idle_forever" in text, f"{script} lacks graceful-idle guard"

    def test_entrypoint_gates_every_collector(self):
        text = ENTRYPOINT.read_text(encoding="utf-8")
        for env in ("ENABLE_RAPL_POWER", "ENABLE_DRAM_BW", "ENABLE_DISK_IO",
                    "ENABLE_NET_IO", "ENABLE_INTERRUPTS", "ENABLE_TEMP_STATS",
                    "ENABLE_PSYS_POWER", "ENABLE_GPU_THROTTLE", "ENABLE_TURBOSTAT"):
            assert env in text, f"entrypoint.sh does not gate on {env}"

    def test_turbostat_interval_uses_env_var_with_default(self):
        # Without a default, plain `docker run` (no TURBOSTAT_INTERVAL) fails
        # Telegraf config parsing with `invalid duration "${TURBOSTAT_INTERVAL}s"`.
        text = (self.TELEGRAF_D / "60-turbostat.conf").read_text(encoding="utf-8")
        assert 'interval = "${TURBOSTAT_INTERVAL:-5}s"' in text

    @staticmethod
    def _turbostat_gate_script(turbostat_path: str) -> str:
        """Extract is_enabled() and the turbostat gate from entrypoint.sh so the
        real shell logic can be exercised against a fake binary path."""
        text = ENTRYPOINT.read_text(encoding="utf-8")
        is_enabled = re.search(r"^is_enabled\(\) \{.*?^\}\n", text, re.S | re.M)
        gate = re.search(
            r"^TURBOSTAT_PATH=/usr/local/bin/turbostat\n.*?^fi\n", text, re.S | re.M
        )
        assert is_enabled and gate, "turbostat gate not found in entrypoint.sh"
        gate_src = gate.group(0).replace(
            "TURBOSTAT_PATH=/usr/local/bin/turbostat",
            f"TURBOSTAT_PATH={shlex.quote(turbostat_path)}",
        )
        return is_enabled.group(0) + gate_src + 'echo "RESULT=$ENABLE_TURBOSTAT"\n'

    @pytest.mark.parametrize(
        "kind, expected",
        [
            ("missing", "false"),       # TURBOSTAT_BIN unset / not mounted
            ("directory", "false"),     # missing host path -> Docker mounts a dir
            ("empty", "false"),         # empty placeholder file
            ("not_executable", "false"),
            ("failing", "false"),       # e.g. distro wrapper w/o kernel tools
            ("working", "true"),
        ],
    )
    def test_entrypoint_skips_unusable_turbostat(self, tmp_path, kind, expected):
        if shutil.which("bash") is None or shutil.which("timeout") is None:
            pytest.skip("bash/timeout not available")
        target = tmp_path / "turbostat"
        if kind == "directory":
            target.mkdir()
        elif kind == "empty":
            target.touch(mode=0o755)
        elif kind == "not_executable":
            target.write_text("#!/bin/sh\nexit 0\n")
            target.chmod(0o644)
        elif kind in ("failing", "working"):
            target.write_text(f"#!/bin/sh\nexit {2 if kind == 'failing' else 0}\n")
            target.chmod(0o755)

        result = subprocess.run(
            ["bash", "-c", self._turbostat_gate_script(str(target))],
            env={"PATH": os.environ.get("PATH", ""), "ENABLE_TURBOSTAT": "true"},
            capture_output=True, text=True, timeout=30, check=True,
        )
        assert f"RESULT={expected}" in result.stdout
        if expected == "false":
            assert "[WARN]  60-turbostat" in result.stdout

    def test_disk_io_restricted_to_physical_devices(self):
        text = (self.TELEGRAF_D / "30-disk.conf").read_text(encoding="utf-8")
        match = re.search(r"^\s*devices\s*=\s*(\[.*\])\s*$", text, re.M)
        assert match, "30-disk.conf must set a default `devices` filter"
        patterns = json.loads(match.group(1))

        def matches(dev: str) -> bool:
            return any(fnmatch.fnmatchcase(dev, p) for p in patterns)

        for dev in ("nvme0n1", "nvme1n1", "sda", "vdb", "mmcblk0"):
            assert matches(dev), f"{dev} should be collected"
        for dev in ("loop0", "loop21", "dm-0", "zd0", "ram0", "sr0",
                    "nvme0n1p1", "sda1", "mmcblk0p1"):
            assert not matches(dev), f"{dev} should be filtered out"

    def test_temp_stats_are_opt_in_dropin(self):
        base_text = (REPO_ROOT / "telegraf.conf").read_text(encoding="utf-8")
        dropin_text = (self.TELEGRAF_D / "70-temp-stats.conf").read_text(encoding="utf-8")
        assert 'interval = "100ms"' not in base_text
        assert "[[aggregators.basicstats]]" not in base_text
        assert 'interval = "100ms"' in dropin_text
        assert "[[aggregators.basicstats]]" in dropin_text

    def test_entrypoint_exports_enable_gpu_throttle(self):
        # ENABLE_GPU_THROTTLE must be gated separately from ENABLE_PSYS_POWER.
        text = ENTRYPOINT.read_text(encoding="utf-8")
        assert "ENABLE_GPU_THROTTLE" in text
        assert "91-gpu-throttle" in text


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
