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
4. The pure per-sample calculation (``compute_npu_sample`` /
   ``format_line_protocol``) is correct for the bandwidth rate, the 32-bit
   counter rollover, and the "omitted when unsupported" behavior for
   ``utilization`` / ``memory_mb`` — these run without any hardware.
"""

import importlib.util
import os
import re
import sys
import tempfile
import types
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


@pytest.fixture(scope="module")
def npu_reader_module():
    """Import npu_reader.py as a module, without real NPU hardware.

    ``npu_reader.py`` does ``sys.path.insert(0, '/app')`` and
    ``from npu_monitor_tool import PmtTelemetry`` at import time, which
    would fail outside the container. We pre-populate ``sys.modules`` with
    a stub ``npu_monitor_tool`` (exposing just the names the reader
    imports) so the module under test loads cleanly in any environment.
    """
    stub = types.ModuleType("npu_monitor_tool")

    class _StubPmtTelemetry:  # pragma: no cover - not exercised, import-only stub
        pass

    class _StubCpuGen:  # pragma: no cover - not exercised, import-only stub
        PTL = 3

    stub.PmtTelemetry = _StubPmtTelemetry
    stub.CpuGen = _StubCpuGen
    sys.modules.setdefault("npu_monitor_tool", stub)

    # npu_reader.py opens a FileHandler at import time, pointed at
    # NPU_READER_LOG_FILE (default /app/npu_reader_trace.log, which only
    # exists inside the container). Redirect it to a writable tmp path so
    # the module can be imported in any environment.
    with tempfile.TemporaryDirectory() as tmp_dir:
        os.environ["NPU_READER_LOG_FILE"] = str(Path(tmp_dir) / "npu_reader_trace.log")
        spec = importlib.util.spec_from_file_location(
            "npu_reader_under_test", READER_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module


@pytest.fixture(scope="module")
def real_lib():
    """Load the real npu_monitor_tool under a private name (no /sys access).

    A distinct module name avoids clobbering the ``npu_monitor_tool`` stub
    that ``npu_reader_module`` may have registered in ``sys.modules``.
    """
    spec = importlib.util.spec_from_file_location(
        "npu_monitor_tool_for_reader_tests", LIB_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        # "utilization" and "memory_mb" are conditionally included (omitted
        # when unsupported — see TestComputeNpuSample) but the field name
        # literals must still be present in the source.
        for field in (
            "power=",
            "frequency_mhz=",
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


class TestComputeNpuSample:
    """Unit tests for the pure per-sample calculation — no hardware needed."""

    def _base_kwargs(self, npu_reader_module, **overrides):
        kwargs = dict(
            elapsed_s=1.0,
            curr_energy=10.0,
            prev_energy=5.0,
            curr_bandwidth_mb=100.0,
            prev_bandwidth_mb=90.0,
            freq_mhz=700.0,
            temp_c=55,
            tile_config=3,
            curr_busy_us=500_000,
            prev_busy_us=400_000,
            mem_util_bytes=2 * 1024 * 1024,
        )
        kwargs.update(overrides)
        return kwargs

    def test_power_is_energy_delta_over_elapsed_seconds(self, npu_reader_module):
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(npu_reader_module, curr_energy=10.0, prev_energy=5.0, elapsed_s=2.0)
        )
        assert fields["power"] == pytest.approx(2.5)

    def test_bandwidth_is_a_rate_divided_by_elapsed_seconds(self, npu_reader_module):
        # delta = 100 - 90 = 10 MB over 2s elapsed -> 5 MB/s, not 10 MB/s.
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(
                npu_reader_module,
                curr_bandwidth_mb=100.0,
                prev_bandwidth_mb=90.0,
                elapsed_s=2.0,
            )
        )
        assert fields["bandwidth"] == pytest.approx(5.0)

    def test_bandwidth_counter_rollover_is_corrected(self, npu_reader_module):
        # The underlying 32-bit counter wrapped: prev > curr even though the
        # counter is still advancing. The corrected delta must be positive
        # and reflect wraparound, not a raw negative delta.
        counter_max = npu_reader_module.NPU_BANDWIDTH_COUNTER_MAX_MB
        prev = counter_max - 5.0
        curr = 10.0  # wrapped around and advanced by 15 MB total
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(
                npu_reader_module,
                curr_bandwidth_mb=curr,
                prev_bandwidth_mb=prev,
                elapsed_s=1.0,
            )
        )
        assert fields["bandwidth"] == pytest.approx(15.0)
        assert fields["bandwidth"] > 0

    def test_frequency_mhz_field_carries_mhz_value_unchanged(self, npu_reader_module):
        # freq_mhz is passed straight through — no rescaling.
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(npu_reader_module, freq_mhz=1234.5)
        )
        assert fields["frequency_mhz"] == pytest.approx(1234.5)
        assert "frequency" not in fields

    def test_utilization_omitted_when_busy_time_unsupported(self, npu_reader_module):
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(npu_reader_module, curr_busy_us=None, prev_busy_us=None)
        )
        assert "utilization" not in fields

    def test_utilization_omitted_when_either_read_failed(self, npu_reader_module):
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(npu_reader_module, curr_busy_us=None, prev_busy_us=400_000)
        )
        assert "utilization" not in fields

    def test_utilization_present_and_correct_when_supported(self, npu_reader_module):
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(
                npu_reader_module,
                curr_busy_us=600_000,
                prev_busy_us=400_000,
                elapsed_s=1.0,
            )
        )
        # delta=200_000us over interval_us=1_000_000 -> 20%
        assert fields["utilization"] == 20

    def test_memory_mb_omitted_when_unsupported(self, npu_reader_module):
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(npu_reader_module, mem_util_bytes=None)
        )
        assert "memory_mb" not in fields

    def test_memory_mb_present_and_correct_when_supported(self, npu_reader_module):
        fields = npu_reader_module.compute_npu_sample(
            **self._base_kwargs(npu_reader_module, mem_util_bytes=4 * 1024 * 1024)
        )
        assert fields["memory_mb"] == pytest.approx(4.0)

    def test_rejects_non_positive_elapsed_seconds(self, npu_reader_module):
        with pytest.raises(ValueError):
            npu_reader_module.compute_npu_sample(
                **self._base_kwargs(npu_reader_module, elapsed_s=0)
            )


class TestFrequencyWiring:
    """Regression: the reader must report the NPU clock in MHz.

    Uses the real ``PmtTelemetry`` decode path (loaded from
    ``scripts/npu_monitor_tool.py`` under a private module name so it does
    not clash with the stub in ``sys.modules``) with a hand-built telemetry
    buffer, so the reader -> getter wiring is covered end to end.
    """

    @staticmethod
    def _make_pmt(lib, cpu_gen, regs, workpoint_raw):
        pmt = lib.PmtTelemetry.__new__(lib.PmtTelemetry)
        buf = bytearray(4096)
        offset = regs["VPU_WORKPOINT"]
        buf[offset : offset + 8] = workpoint_raw.to_bytes(8, "little")
        pmt.buffer = bytes(buf)
        pmt.cpu_gen = cpu_gen
        pmt.regs = regs
        pmt.pmt_root = "/sys/class/intel_pmt"
        pmt.telemetry_path = None
        return pmt

    def test_mtl_workpoint_42_reports_1400_mhz(self, real_lib):
        pmt = self._make_pmt(
            real_lib, real_lib.CpuGen.MTL, real_lib.get_mtl_regs(), workpoint_raw=42
        )
        assert pmt.get_freq_mhz() == pytest.approx(1400.0)

    def test_frequency_mhz_flows_into_line_protocol(self, npu_reader_module, real_lib):
        pmt = self._make_pmt(
            real_lib, real_lib.CpuGen.MTL, real_lib.get_mtl_regs(), workpoint_raw=42
        )
        fields = npu_reader_module.compute_npu_sample(
            elapsed_s=1.0,
            curr_energy=1.0,
            prev_energy=0.0,
            curr_bandwidth_mb=0.0,
            prev_bandwidth_mb=0.0,
            freq_mhz=pmt.get_freq_mhz(),
            temp_c=50,
            tile_config=1,
            curr_busy_us=None,
            prev_busy_us=None,
            mem_util_bytes=None,
        )
        line = npu_reader_module.format_line_protocol("host1", fields, 1)
        assert "frequency_mhz=1400.0" in line

    def test_main_loop_uses_mhz_getter(self, reader_source):
        # Guard the call site in main(): the loop must use the MHz getter,
        # and the removed legacy getters must not come back.
        assert "freq_mhz=pu.get_freq_mhz()" in reader_source
        assert "get_freq()" not in reader_source
        assert "get_display_freq_hz" not in reader_source


class TestFormatLineProtocol:
    def test_omits_utilization_and_memory_mb_when_absent(self, npu_reader_module):
        fields = {
            "power": 1.0,
            "frequency_mhz": 700.0,
            "temperature": 50,
            "bandwidth": 2.0,
            "tile_config": 1,
        }
        line = npu_reader_module.format_line_protocol("host1", fields, 123)
        assert "utilization=" not in line
        assert "memory_mb=" not in line
        assert line.startswith("npu,host=host1 ")
        assert line.endswith(" 123")

    def test_includes_utilization_and_memory_mb_when_present(self, npu_reader_module):
        fields = {
            "power": 1.0,
            "frequency_mhz": 700.0,
            "temperature": 50,
            "bandwidth": 2.0,
            "tile_config": 1,
            "utilization": 42,
            "memory_mb": 3.5,
        }
        line = npu_reader_module.format_line_protocol("host1", fields, 123)
        assert "utilization=42i" in line
        assert "memory_mb=3.50" in line


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
   # Expect: npu_power, npu_frequency_mhz, npu_temperature, npu_bandwidth,
   #         npu_tile_config, npu_utilization, npu_memory_mb
   # npu_utilization / npu_memory_mb may be absent on platforms where the
   # underlying sysfs node isn't supported — that's the documented
   # "omitted when unsupported" behavior, not a bug.

5. Confirm they flow through the service API:
   curl -s http://localhost:9090/api/v1/metrics/latest | \
     jq '.metrics | to_entries[] | select(.key == "npu")'

6. On a host without an NPU, the reader exits via sys.exit(1) from
   PmtTelemetry.__init__ — Telegraf logs the failure but the rest of the
   service keeps running.
"""
