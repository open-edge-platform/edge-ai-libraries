# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Tests for scripts/rapl_reader.py — the RAPL psys/package power execd reader.

RaplZone and discover_zones() read sysfs, so each test builds a fake powercap
tree under tmp_path and drives the clock explicitly.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

WRAP_RANGE = 262_143_328_850  # typical max_energy_range_uj


@pytest.fixture
def rapl(load_reader):
    return load_reader("rapl_reader", "RAPL_READER_LOG_FILE")


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now


def make_zone_dir(root: Path, name: str, energy_uj, zone_name="package-0", max_range=WRAP_RANGE) -> Path:
    zone = root / name
    zone.mkdir(parents=True)
    (zone / "name").write_text(f"{zone_name}\n")
    if energy_uj is not None:
        (zone / "energy_uj").write_text(f"{energy_uj}\n")
    if max_range is not None:
        (zone / "max_energy_range_uj").write_text(f"{max_range}\n")
    return zone


@pytest.fixture
def clock(rapl, monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(rapl, "time", SimpleNamespace(monotonic=fake.monotonic))
    return fake


class TestRaplZonePowerW:
    def test_normal_delta(self, rapl, clock, tmp_path):
        zone_dir = make_zone_dir(tmp_path, "intel-rapl:0", energy_uj=1_000_000)
        zone = rapl.RaplZone(str(zone_dir))

        clock.now += 2.0
        (zone_dir / "energy_uj").write_text("3000000")

        assert zone.power_w() == pytest.approx(1.0)  # 2 J over 2 s

    def test_successive_calls_use_the_previous_sample(self, rapl, clock, tmp_path):
        zone_dir = make_zone_dir(tmp_path, "intel-rapl:0", energy_uj=0)
        zone = rapl.RaplZone(str(zone_dir))
        for energy, expected in ((5_000_000, 5.0), (7_000_000, 2.0)):
            clock.now += 1.0
            (zone_dir / "energy_uj").write_text(str(energy))
            assert zone.power_w() == pytest.approx(expected)

    def test_counter_wraparound_adds_max_range(self, rapl, clock, tmp_path):
        zone_dir = make_zone_dir(tmp_path, "intel-rapl:0", energy_uj=WRAP_RANGE - 500_000)
        zone = rapl.RaplZone(str(zone_dir))

        clock.now += 1.0
        (zone_dir / "energy_uj").write_text("1500000")  # wrapped past max_energy_range_uj

        assert zone.power_w() == pytest.approx(2.0)  # 500k + 1.5M uJ in 1 s

    def test_wraparound_without_max_range_is_dropped(self, rapl, clock, tmp_path):
        zone_dir = make_zone_dir(tmp_path, "intel-rapl:0", energy_uj=9_000_000, max_range=None)
        zone = rapl.RaplZone(str(zone_dir))

        clock.now += 1.0
        (zone_dir / "energy_uj").write_text("1000")

        assert zone.power_w() is None

    def test_zero_time_delta_returns_none(self, rapl, clock, tmp_path):
        zone_dir = make_zone_dir(tmp_path, "intel-rapl:0", energy_uj=1_000_000)
        zone = rapl.RaplZone(str(zone_dir))
        (zone_dir / "energy_uj").write_text("2000000")
        # clock not advanced

        assert zone.power_w() is None

    def test_unreadable_counter_returns_none_then_recovers(self, rapl, clock, tmp_path):
        zone_dir = make_zone_dir(tmp_path, "intel-rapl:0", energy_uj=1_000_000)
        zone = rapl.RaplZone(str(zone_dir))

        clock.now += 1.0
        (zone_dir / "energy_uj").write_text("not a number")
        assert zone.power_w() is None

        clock.now += 1.0
        (zone_dir / "energy_uj").write_text("3000000")
        assert zone.power_w() is None  # no baseline yet after the failed read

        clock.now += 1.0
        (zone_dir / "energy_uj").write_text("4000000")
        assert zone.power_w() == pytest.approx(1.0)


class TestRaplZoneMetadata:
    def test_name_and_readable(self, rapl, tmp_path):
        zone = rapl.RaplZone(str(make_zone_dir(tmp_path, "intel-rapl:1", 10, zone_name="psys")))
        assert zone.name == "psys"
        assert zone.readable is True
        assert zone.max_range == WRAP_RANGE

    def test_missing_energy_file_is_not_readable(self, rapl, tmp_path):
        zone = rapl.RaplZone(str(make_zone_dir(tmp_path, "intel-rapl:0", None)))
        assert zone.readable is False

    def test_name_falls_back_to_directory_name(self, rapl, tmp_path):
        zone_dir = make_zone_dir(tmp_path, "intel-rapl:0", 10)
        (zone_dir / "name").unlink()
        assert rapl.RaplZone(str(zone_dir)).name == "intel-rapl:0"


class TestDiscoverZones:
    def test_top_level_zones_only_and_unreadable_skipped(self, rapl, monkeypatch, tmp_path):
        make_zone_dir(tmp_path, "intel-rapl:0", 1, zone_name="package-0")
        make_zone_dir(tmp_path, "intel-rapl:0:0", 1, zone_name="core")  # sub-domain
        make_zone_dir(tmp_path, "intel-rapl:1", 1, zone_name="psys")
        make_zone_dir(tmp_path, "intel-rapl:2", None, zone_name="locked")  # no energy_uj
        monkeypatch.setattr(rapl, "RAPL_GLOB", str(tmp_path / "intel-rapl:*"))

        assert [z.name for z in rapl.discover_zones()] == ["package-0", "psys"]
