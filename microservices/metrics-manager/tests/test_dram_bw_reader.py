# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Tests for scripts/dram_bw_reader.py — the perf-based DRAM bandwidth execd reader.

The perf-output parser and the sampling wrapper are exercised without perf or an
IMC PMU: `perf stat -x,` stderr is supplied as text and subprocess.run is faked.
"""

import subprocess
from types import SimpleNamespace

import pytest

MIB = 1024 * 1024
READ_LINE = "{},MiB,uncore_imc_free_running/data_read/,1000000000,100.00,,"
WRITE_LINE = "{},MiB,uncore_imc_free_running/data_write/,1000000000,100.00,,"


@pytest.fixture
def dram(load_reader):
    return load_reader("dram_bw_reader", "DRAM_BW_READER_LOG_FILE")


class TestParsePerfValue:
    def test_mib_lines_are_converted_to_bytes(self, dram):
        stderr = READ_LINE.format("116.6") + "\n" + WRITE_LINE.format("7.4") + "\n"
        assert dram._parse_perf_value(stderr, dram.READ_EVENT) == pytest.approx(116.6 * MIB)
        assert dram._parse_perf_value(stderr, dram.WRITE_EVENT) == pytest.approx(7.4 * MIB)

    def test_event_selected_by_alias_not_by_position(self, dram):
        stderr = WRITE_LINE.format("7.4") + "\n" + READ_LINE.format("116.6") + "\n"
        assert dram._parse_perf_value(stderr, dram.READ_EVENT) == pytest.approx(116.6 * MIB)

    def test_other_units(self, dram):
        kib = "2048,KiB,uncore_imc_free_running/data_read/,1,100.00,,"
        raw = "4096,,uncore_imc_free_running/data_read/,1,100.00,,"
        assert dram._parse_perf_value(kib, dram.READ_EVENT) == 2048 * 1024
        assert dram._parse_perf_value(raw, dram.READ_EVENT) == 4096

    def test_multiple_lines_for_one_event_are_summed(self, dram):
        stderr = READ_LINE.format("10") + "\n" + READ_LINE.format("5") + "\n"
        assert dram._parse_perf_value(stderr, dram.READ_EVENT) == pytest.approx(15 * MIB)

    @pytest.mark.parametrize("marker", ["<not counted>", "<not supported>"])
    def test_uncounted_event_returns_sentinel(self, dram, marker):
        stderr = f"{marker},,uncore_imc_free_running/data_read/,0,100.00,,"
        assert dram._parse_perf_value(stderr, dram.READ_EVENT) == -1.0

    @pytest.mark.parametrize("stderr", ["", "\n\n", "perf: command not found", "garbage,line"])
    def test_empty_or_unparseable_input_returns_sentinel(self, dram, stderr):
        assert dram._parse_perf_value(stderr, dram.READ_EVENT) == -1.0

    def test_non_numeric_count_is_skipped(self, dram):
        stderr = "abc,MiB,uncore_imc_free_running/data_read/,1,100.00,,"
        assert dram._parse_perf_value(stderr, dram.READ_EVENT) == -1.0

    def test_zero_is_a_valid_count_not_a_sentinel(self, dram):
        assert dram._parse_perf_value(READ_LINE.format("0"), dram.READ_EVENT) == 0.0

    def test_locale_decimal_comma_is_repaired(self, dram):
        # A decimal-comma locale makes perf print "116,6" and the CSV split in two.
        stderr = READ_LINE.format("116,6") + "\n" + WRITE_LINE.format("7,4") + "\n"
        assert dram._parse_perf_value(stderr, dram.READ_EVENT) == pytest.approx(116.6 * MIB)
        assert dram._parse_perf_value(stderr, dram.WRITE_EVENT) == pytest.approx(7.4 * MIB)


class TestSampleOnce:
    @staticmethod
    def _fake_run(stderr, calls):
        def run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return SimpleNamespace(stderr=stderr, returncode=0)

        return run

    def test_emits_line_protocol_in_gb_per_s(self, dram, monkeypatch):
        monkeypatch.setattr(dram, "INTERVAL_S", 2.0)
        monkeypatch.setattr(dram, "HOST_TAG", "node1")
        stderr = READ_LINE.format("1000") + "\n" + WRITE_LINE.format("500") + "\n"
        calls = []
        monkeypatch.setattr(dram.subprocess, "run", self._fake_run(stderr, calls))

        line = dram.sample_once()

        read_gbps = 1000 * MIB / 2.0 / 1e9
        write_gbps = 500 * MIB / 2.0 / 1e9
        assert line.startswith("dram_bw,host=node1 ")
        assert f"read_gbps={read_gbps:.4f}" in line
        assert f"write_gbps={write_gbps:.4f}" in line
        assert f"total_gbps={read_gbps + write_gbps:.4f}" in line

    def test_perf_runs_with_c_locale(self, dram, monkeypatch):
        calls = []
        monkeypatch.setattr(dram.subprocess, "run", self._fake_run(READ_LINE.format("1"), calls))
        dram.sample_once()
        assert calls[0][1]["env"]["LC_ALL"] == "C"
        assert calls[0][0][0] == "perf"

    def test_one_uncounted_event_still_reports_the_other(self, dram, monkeypatch):
        stderr = READ_LINE.format("100") + "\n<not counted>,,uncore_imc_free_running/data_write/,0,0,,\n"
        monkeypatch.setattr(dram.subprocess, "run", self._fake_run(stderr, []))
        monkeypatch.setattr(dram, "INTERVAL_S", 1.0)
        line = dram.sample_once()
        assert f"read_gbps={100 * MIB / 1e9:.4f}" in line
        assert "write_gbps=0.0000" in line

    def test_no_counts_returns_empty_string(self, dram, monkeypatch):
        monkeypatch.setattr(dram.subprocess, "run", self._fake_run("nothing useful", []))
        assert dram.sample_once() == ""

    @pytest.mark.parametrize("exc", [OSError("no perf"), subprocess.TimeoutExpired("perf", 1)])
    def test_perf_failure_returns_empty_string(self, dram, monkeypatch, exc):
        def boom(*args, **kwargs):
            raise exc

        monkeypatch.setattr(dram.subprocess, "run", boom)
        assert dram.sample_once() == ""


class TestPmuAvailable:
    def test_prefix_match_on_numbered_instances(self, dram, monkeypatch):
        monkeypatch.setattr(dram.os, "listdir", lambda _: ["cpu", "uncore_imc_free_running_0"])
        assert dram._pmu_available() is True

    def test_skylake_style_imc_without_free_running_pmu(self, dram, monkeypatch):
        monkeypatch.setattr(dram.os, "listdir", lambda _: ["cpu", "uncore_imc_0", "uncore_imc_1"])
        assert dram._pmu_available() is False

    def test_missing_sysfs_dir(self, dram, monkeypatch):
        def raise_oserror(_):
            raise OSError

        monkeypatch.setattr(dram.os, "listdir", raise_oserror)
        assert dram._pmu_available() is False
