# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Tests for scripts/npu_reader.py — the Telegraf execd input that emits NPU
metrics in InfluxDB Line Protocol.

Full execution requires real NPU hardware (/sys/class/intel_pmt), a writable
/app for the trace log, and can only be exercised inside the container. These
tests therefore verify:
1. The script parses as valid Python (guards against syntax regressions).
2. The expected wiring between the reader, the PmtTelemetry library, and
   telegraf.conf is intact.
3. The reader emits an `npu` measurement with the documented fields.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
READER_PATH = SCRIPTS_DIR / "npu_reader.py"
LIB_PATH = SCRIPTS_DIR / "npu_monitor_tool.py"
TELEGRAF_CONF = PROJECT_ROOT / "telegraf.conf"


@pytest.fixture(scope="module")
def reader_source() -> str:
    return READER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def telegraf_conf() -> str:
    return TELEGRAF_CONF.read_text(encoding="utf-8")


class TestScriptFiles:
    def test_reader_file_exists(self):
        assert READER_PATH.is_file(), f"Reader script missing: {READER_PATH}"

    def test_library_file_exists(self):
        # Note the underscore — `from npu_monitor_tool import PmtTelemetry`
        # only works when the library is named with an underscore.
        assert LIB_PATH.is_file(), f"PmtTelemetry library missing: {LIB_PATH}"

    def test_reader_is_valid_python(self, reader_source):
        compile(reader_source, str(READER_PATH), "exec")


class TestReaderImportsAndOutput:
    def test_imports_pmt_telemetry_with_underscore_module_name(self, reader_source):
        assert "from npu_monitor_tool import PmtTelemetry" in reader_source

    def test_conditionally_imports_cpu_gen_for_memory_util_gate(self, reader_source):
        assert "from npu_monitor_tool import CpuGen" in reader_source

    def test_hostname_supports_env_override(self, reader_source):
        # The HOSTNAME constant must honour METRICS_MANAGER_HOSTNAME so users
        # can keep dashboards stable across reboots when the kernel hostname
        # changes. See docs/CONFIGURATION.md (METRICS_MANAGER_HOSTNAME).
        assert 'os.environ.get("METRICS_MANAGER_HOSTNAME")' in reader_source
        assert "or os.uname()[1]" in reader_source

    def test_emits_npu_measurement_in_influx_line_protocol(self, reader_source):
        # The measurement name and the host tag are the contract between
        # the reader and Telegraf's `data_format = "influx"` parser.
        assert 'f"npu,host=' in reader_source

    def test_emits_all_documented_fields(self, reader_source):
        # These field names are consumed by Prometheus downstream and are
        # part of the public metric surface — breakage would silently drop data.
        for field in (
            "power=",
            "frequency=",
            "temperature=",
            "bandwidth=",
            "tile_config=",
            "utilization=",
            "memory_mb=",
        ):
            assert field in reader_source, f"Missing field '{field}' in reader output"


class TestTelegrafWiring:
    def test_telegraf_conf_invokes_reader(self, telegraf_conf):
        assert "/app/scripts/npu_reader.py" in telegraf_conf

    def test_reader_is_configured_as_execd_with_influx_format(self, telegraf_conf):
        # The reader is a long-running process that streams to stdout, so it
        # MUST be wired as `inputs.execd` (not `inputs.exec`) with influx format.
        pattern = re.compile(
            r"\[\[inputs\.execd\]\]\s*"
            r"\n\s*command\s*=\s*\[\"python3\",\s*\"/app/scripts/npu_reader\.py\"\]"
            r"\s*\n\s*data_format\s*=\s*\"influx\"",
            re.MULTILINE,
        )
        assert pattern.search(telegraf_conf), (
            "Expected NPU reader wired as [[inputs.execd]] with python3 command "
            "and data_format='influx'"
        )


# Manual integration test (Docker / real NPU required):
"""
To manually verify NPU metrics on an NPU-equipped host:

1. Start the service:
   docker compose up --build

2. Check the reader is running:
   docker exec metrics-manager ps -ef | grep npu_reader

3. Inspect the reader's trace log:
   docker exec metrics-manager cat /app/npu_reader_trace.log

4. Confirm NPU metrics on the Prometheus endpoint:
   curl -s http://localhost:9273/metrics | grep '^npu_'
   # Expect: npu_power, npu_frequency, npu_temperature, npu_bandwidth,
   #         npu_tile_config, npu_utilization, npu_memory_mb

5. Confirm they flow through the service API:
   curl -s http://localhost:9090/api/v1/metrics/latest | \
     jq '.metrics | to_entries[] | select(.key == "npu")'

6. On a host without an NPU, the reader exits via sys.exit(1) from
   PmtTelemetry.__init__ — Telegraf logs the failure but the rest of the
   service keeps running.
"""
