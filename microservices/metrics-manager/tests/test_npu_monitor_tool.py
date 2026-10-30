# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for scripts/npu_monitor_tool.py (PmtTelemetry class and helpers).

The script lives under scripts/ (no __init__.py) so we load it via importlib.
Tests focus on pure logic: bit slicing, register maps, value decoding, and
helpers — without touching /sys or requiring real NPU hardware.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "npu_monitor_tool.py"


@pytest.fixture(scope="module")
def npu_mod():
    """Load scripts/npu_monitor_tool.py as a module once per test module."""
    spec = importlib.util.spec_from_file_location("npu_monitor_tool", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["npu_monitor_tool"] = module
    spec.loader.exec_module(module)
    return module


def _make_pmt(npu_mod, buffer, cpu_gen=None, regs=None):
    """Build a PmtTelemetry instance skipping __init__ (which needs /sys/class/intel_pmt)."""
    pmt = npu_mod.PmtTelemetry.__new__(npu_mod.PmtTelemetry)
    pmt.buffer = buffer
    pmt.cpu_gen = cpu_gen if cpu_gen is not None else npu_mod.CpuGen.PTL
    pmt.regs = regs if regs is not None else npu_mod.get_ptl_regs()
    pmt.pmt_root = "/sys/class/intel_pmt"
    pmt.telemetry_path = None
    return pmt


def _buffer_with(overrides, size=4096):
    """Return a bytes buffer of `size` with the given {offset: bytes} overrides."""
    buf = bytearray(size)
    for offset, data in overrides.items():
        buf[offset : offset + len(data)] = data
    return bytes(buf)


class TestRegisterMaps:
    def test_mtl_regs_has_expected_keys(self, npu_mod):
        expected = {"VPU_ENERGY", "SOC_TEMPERATURES", "VPU_WORKPOINT", "VPU_MEMORY_BW"}
        assert set(npu_mod.get_mtl_regs()) == expected

    def test_arl_regs_equals_mtl(self, npu_mod):
        assert npu_mod.get_arl_regs() == npu_mod.get_mtl_regs()

    def test_lnl_regs_values(self, npu_mod):
        assert npu_mod.get_lnl_regs() == {
            "VPU_ENERGY": 0x5D0,
            "SOC_TEMPERATURES": 0x70,
            "VPU_WORKPOINT": 0x18,
            "VPU_MEMORY_BW": 0xC18,
        }

    def test_ptl_regs_values(self, npu_mod):
        assert npu_mod.get_ptl_regs() == {
            "VPU_ENERGY": 0x670,
            "SOC_TEMPERATURES": 0x78,
            "VPU_WORKPOINT": 0x18,
            "VPU_MEMORY_BW": 0xC18,
        }

    def test_pmt_guids_are_declared(self, npu_mod):
        # All platforms we support should have a GUID constant
        assert npu_mod.PMT_GUID_MTL == "0x130670b2"
        assert npu_mod.PMT_GUID_ARL == "0x1306a0b3"
        assert npu_mod.PMT_GUID_ARL_H == "0x1306a0b2"
        assert npu_mod.PMT_GUID_ARL_S == "0x1306a0b4"
        assert npu_mod.PMT_GUID_LNL == "0x3072005"
        assert npu_mod.PMT_GUID_PTL == "0x3086000"


class TestCpuGen:
    def test_string_representations(self, npu_mod):
        assert str(npu_mod.CpuGen.MTL) == "Meteor Lake"
        assert str(npu_mod.CpuGen.ARL) == "Arrow Lake"
        assert str(npu_mod.CpuGen.LNL) == "Lunar Lake"
        assert str(npu_mod.CpuGen.PTL) == "Panther Lake"

    def test_ordering_matches_generation(self, npu_mod):
        # PTL is the newest, MTL the oldest — npu_reader uses `>= PTL` to gate memory util
        g = npu_mod.CpuGen
        assert g.MTL < g.ARL < g.LNL < g.PTL


class TestBitSlicing:
    def test_read_low_byte(self, npu_mod):
        buf = _buffer_with({0: b"\xab\x00\x00\x00\x00\x00\x00\x00"})
        assert _make_pmt(npu_mod, buf).read(0, 7, 0) == 0xAB

    def test_read_byte_1(self, npu_mod):
        buf = _buffer_with({0: b"\x00\x2a\x00\x00\x00\x00\x00\x00"})
        assert _make_pmt(npu_mod, buf).read(0, 15, 8) == 0x2A

    def test_read_high_byte(self, npu_mod):
        buf = _buffer_with({0: b"\x00\x00\x00\x00\x00\x00\x00\x80"})
        assert _make_pmt(npu_mod, buf).read(0, 63, 56) == 0x80

    def test_read_full_qword(self, npu_mod):
        buf = _buffer_with({0: b"\xef\xcd\xab\x89\x67\x45\x23\x01"})
        assert _make_pmt(npu_mod, buf).read(0, 63, 0) == 0x0123456789ABCDEF

    def test_read_with_nonzero_offset(self, npu_mod):
        buf = _buffer_with({0x100: b"\x7f\x00\x00\x00\x00\x00\x00\x00"})
        assert _make_pmt(npu_mod, buf).read(0x100, 7, 0) == 0x7F


class TestGetters:
    def test_get_freq_hz_ptl_uses_lnl_buttress_formula(self, npu_mod):
        # raw = 100 at low byte of VPU_WORKPOINT (PTL: 0x18) -> 100 * 50 MHz / 2
        buf = _buffer_with({0x18: b"\x64\x00\x00\x00\x00\x00\x00\x00"})
        pmt = _make_pmt(npu_mod, buf)
        freq = pmt.get_freq_hz()
        assert isinstance(freq, float)
        assert freq == 2_500_000_000.0

    def test_get_freq_hz_lnl_uses_lnl_buttress_formula(self, npu_mod):
        # raw = 78 at LNL VPU_WORKPOINT (0x18) -> 1950 MHz
        buf = _buffer_with({0x18: b"\x4e\x00\x00\x00\x00\x00\x00\x00"})
        pmt = _make_pmt(
            npu_mod, buf, cpu_gen=npu_mod.CpuGen.LNL, regs=npu_mod.get_lnl_regs()
        )
        assert pmt.get_freq_hz() == 1_950_000_000.0

    def test_get_freq_hz_mtl_uses_mtl_buttress_formula(self, npu_mod):
        # raw = 42 at low byte of VPU_WORKPOINT (MTL: 0x68) -> 42 * 50 MHz * 2 / 3
        buf = _buffer_with({0x68: b"\x2a\x00\x00\x00\x00\x00\x00\x00"})
        pmt = _make_pmt(
            npu_mod, buf, cpu_gen=npu_mod.CpuGen.MTL, regs=npu_mod.get_mtl_regs()
        )
        assert pmt.get_freq_hz() == 1_400_000_000.0

    def test_get_freq_hz_arl_uses_mtl_buttress_formula(self, npu_mod):
        # ARL shares the MTL buttress in the kernel (ivpu_hw_btrs_gen), so
        # raw = 48 must give 1.6 GHz, not the LNL-formula 48 * 25 MHz = 1.2 GHz.
        buf = _buffer_with({0x68: b"\x30\x00\x00\x00\x00\x00\x00\x00"})
        pmt = _make_pmt(
            npu_mod, buf, cpu_gen=npu_mod.CpuGen.ARL, regs=npu_mod.get_arl_regs()
        )
        assert pmt.get_freq_hz() == 1_600_000_000.0

    @pytest.mark.parametrize(
        "gen_name, raw, expected_hz",
        [
            # MTL buttress: ratio * 50e6 * 2 / 3 (kernel pll_ratio_to_mhz_mtl)
            ("MTL", 42, 1_400_000_000),
            ("ARL", 48, 1_600_000_000),
            ("ARL", 0, 0),               # idle
            # LNL buttress: ratio * 50e6 / 2 (kernel pll_ratio_to_mhz_lnl)
            ("LNL", 78, 1_950_000_000),
            ("PTL", 82, 2_050_000_000),
            ("PTL", 0, 0),               # idle
        ],
    )
    def test_pll_ratio_to_hz_matches_kernel(self, npu_mod, gen_name, raw, expected_hz):
        gen = getattr(npu_mod.CpuGen, gen_name)
        assert npu_mod.pll_ratio_to_hz(gen, raw) == float(expected_hz)

    def test_pll_ratio_to_hz_keeps_fractional_clock(self, npu_mod):
        # The kernel truncates to integer MHz (49 -> 1633 MHz); the exact
        # clock is 4.9e9 / 3 Hz, and no integer truncation must happen here.
        hz = npu_mod.pll_ratio_to_hz(npu_mod.CpuGen.ARL, 49)
        assert hz == pytest.approx(4_900_000_000 / 3)
        assert hz != int(hz)

    def test_mtl_buttress_gens_match_kernel(self, npu_mod):
        assert npu_mod.MTL_BUTTRESS_GENS == {npu_mod.CpuGen.MTL, npu_mod.CpuGen.ARL}

    def test_legacy_freq_getters_removed(self, npu_mod):
        for name in ("get_freq", "get_display_freq_hz", "get_freq_mhz"):
            assert not hasattr(npu_mod.PmtTelemetry, name), name

    def test_get_voltage_reads_byte_1_of_workpoint(self, npu_mod):
        buf = _buffer_with({0x18: b"\x00\x2a\x00\x00\x00\x00\x00\x00"})
        assert _make_pmt(npu_mod, buf).get_voltage() == 42

    def test_get_tile_config_reads_byte_2_of_workpoint(self, npu_mod):
        buf = _buffer_with({0x18: b"\x00\x00\x04\x00\x00\x00\x00\x00"})
        assert _make_pmt(npu_mod, buf).get_tile_config() == 4

    def test_get_npu_temperature_reads_byte_5_of_soc_temps(self, npu_mod):
        # PTL SOC_TEMPERATURES = 0x78; bits 40-47 = byte 5
        buf = _buffer_with({0x78: b"\x00\x00\x00\x00\x00\x37\x00\x00"})
        assert _make_pmt(npu_mod, buf).get_npu_temperature() == 0x37

    def test_get_npu_energy_decodes_u32_18_14_fixed_point(self, npu_mod):
        # Integer part 100, fractional 0.5 → (100 << 14) | 8192
        val = (100 << 14) | 8192
        buf = _buffer_with({0x670: val.to_bytes(8, "little")})
        assert _make_pmt(npu_mod, buf).get_npu_energy() == pytest.approx(100.5)

    def test_get_npu_energy_zero(self, npu_mod):
        buf = _buffer_with({0x670: b"\x00" * 8})
        assert _make_pmt(npu_mod, buf).get_npu_energy() == 0.0

    def test_get_noc_bandwidth_divides_by_1000(self, npu_mod):
        # raw = 1000 at VPU_MEMORY_BW (PTL: 0xC18), bits 0-31
        buf = _buffer_with({0xC18: (1000).to_bytes(8, "little")})
        assert _make_pmt(npu_mod, buf).get_noc_bandwidth() == pytest.approx(1.0)


class TestNocBandwidthRate:
    def test_rate_is_delta_over_elapsed_seconds(self, npu_mod):
        assert npu_mod.noc_bandwidth_rate_mbs(90.0, 100.0, 2.0) == pytest.approx(5.0)

    def test_counter_wrap_is_corrected(self, npu_mod):
        wrap = npu_mod.NOC_BW_COUNTER_WRAP_MB
        assert wrap == pytest.approx((2**32) / 1e3)
        # prev near the top of the 32-bit range, curr wrapped and advanced 15 MB total.
        rate = npu_mod.noc_bandwidth_rate_mbs(wrap - 5.0, 10.0, 1.0)
        assert rate == pytest.approx(15.0)

    def test_zero_delta_is_zero(self, npu_mod):
        assert npu_mod.noc_bandwidth_rate_mbs(42.0, 42.0, 1.0) == 0.0

    @pytest.mark.parametrize("elapsed", [0.0, -1.0])
    def test_rejects_non_positive_elapsed(self, npu_mod, elapsed):
        with pytest.raises(ValueError):
            npu_mod.noc_bandwidth_rate_mbs(0.0, 1.0, elapsed)


class TestCsvCell:
    def test_none_renders_empty_cell(self, npu_mod):
        assert npu_mod.csv_cell(None) == ""
        assert npu_mod.csv_cell(None, ".2f") == ""

    def test_zero_is_kept(self, npu_mod):
        # A real 0 reading must not be confused with "unsupported".
        assert npu_mod.csv_cell(0) == "0"

    def test_format_spec_applied(self, npu_mod):
        assert npu_mod.csv_cell(1.23456, ".2f") == "1.23"


class TestFdump:
    def test_reads_and_strips_file_contents(self, npu_mod, tmp_path):
        f = tmp_path / "sample"
        f.write_text("  42 \n")
        assert npu_mod.fdump(str(f)) == "42"

    def test_missing_file_exits(self, npu_mod, tmp_path):
        with pytest.raises(SystemExit):
            npu_mod.fdump(str(tmp_path / "does-not-exist"))


class TestRunCommand:
    def test_missing_executable_returns_127(self, npu_mod):
        # Portable across Linux and Windows: a clearly non-existent binary
        result = npu_mod.run_command("definitely-not-a-real-binary-xyz arg1")
        assert result.returncode == 127
