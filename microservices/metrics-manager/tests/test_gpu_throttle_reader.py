# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Tests for scripts/gpu_throttle_reader.py — the xe DRM frequency/throttle reader.

GpuFreqDomain.sample() reads sysfs, so each test builds a fake
card*/device/tile*/gt*/freq0 tree under tmp_path.
"""

from pathlib import Path

import pytest


@pytest.fixture
def gpu(load_reader):
    return load_reader("gpu_throttle_reader", "GPU_THROTTLE_READER_LOG_FILE")


def make_freq_dir(root: Path, card="card1", gt="gt0", act=1550, cur=2000, throttle=None) -> Path:
    """Create .../<card>/device/tile0/<gt>/freq0 with optional throttle attrs."""
    freq = root / card / "device" / "tile0" / gt / "freq0"
    freq.mkdir(parents=True)
    if act is not None:
        (freq / "act_freq").write_text(f"{act}\n")
    if cur is not None:
        (freq / "cur_freq").write_text(f"{cur}\n")
    if throttle is not None:
        (freq / "throttle").mkdir()
        for fname, value in throttle.items():
            (freq / "throttle" / fname).write_text(f"{value}\n")
    return freq


class TestSample:
    def test_frequencies_and_throttle_reasons(self, gpu, tmp_path):
        freq = make_freq_dir(
            tmp_path,
            throttle={
                "status": 1,
                "reason_thermal": 1,
                "reason_pl1": 0,
                "reason_pl2": 0,
                "reason_prochot": 0,
            },
        )
        assert gpu.GpuFreqDomain(str(freq)).sample() == {
            "act_freq_mhz": 1550,
            "driver_freq_mhz": 2000,
            "throttled": 1,
            "throttle_thermal": 1,
            "throttle_pl1": 0,
            "throttle_pl2": 0,
            "throttle_prochot": 0,
        }

    def test_without_throttle_directory_only_frequencies(self, gpu, tmp_path):
        freq = make_freq_dir(tmp_path)  # e.g. a driver/kernel that has no throttle/ dir
        assert gpu.GpuFreqDomain(str(freq)).sample() == {
            "act_freq_mhz": 1550,
            "driver_freq_mhz": 2000,
        }

    def test_partial_throttle_attributes(self, gpu, tmp_path):
        freq = make_freq_dir(tmp_path, throttle={"status": 0, "reason_pl1": 0})
        fields = gpu.GpuFreqDomain(str(freq)).sample()
        assert fields["throttled"] == 0 and fields["throttle_pl1"] == 0
        assert "throttle_thermal" not in fields

    def test_non_numeric_attribute_is_skipped(self, gpu, tmp_path):
        freq = make_freq_dir(tmp_path, throttle={"status": "n/a", "reason_thermal": 1})
        fields = gpu.GpuFreqDomain(str(freq)).sample()
        assert "throttled" not in fields and fields["throttle_thermal"] == 1

    def test_only_cur_freq_present(self, gpu, tmp_path):
        freq = make_freq_dir(tmp_path, act=None, cur=900)
        assert gpu.GpuFreqDomain(str(freq)).sample() == {"driver_freq_mhz": 900}

    def test_domain_vanished_returns_none(self, gpu, tmp_path):
        freq = make_freq_dir(tmp_path, act=None, cur=None)
        assert gpu.GpuFreqDomain(str(freq)).sample() is None


class TestDomainIdentity:
    def test_card_and_gt_tags_come_from_the_path(self, gpu, tmp_path):
        freq = make_freq_dir(tmp_path, card="card0", gt="gt1")
        domain = gpu.GpuFreqDomain(str(freq))
        assert (domain.card, domain.gt) == ("card0", "gt1")

    def test_readable_requires_act_freq(self, gpu, tmp_path):
        assert gpu.GpuFreqDomain(str(make_freq_dir(tmp_path))).readable is True
        no_act = make_freq_dir(tmp_path, card="card2", act=None)
        assert gpu.GpuFreqDomain(str(no_act)).readable is False


class TestDiscoverAndFormat:
    def test_discover_domains_skips_unreadable(self, gpu, monkeypatch, tmp_path):
        make_freq_dir(tmp_path, card="card0")
        make_freq_dir(tmp_path, card="card1", act=None)
        monkeypatch.setattr(gpu, "FREQ_GLOB", str(tmp_path / "card*/device/tile*/gt*/freq0"))
        assert [d.card for d in gpu.discover_domains()] == ["card0"]

    def test_discover_domains_empty_on_i915_style_tree(self, gpu, monkeypatch, tmp_path):
        # i915 has no tile*/gt*/freq0 layout, so the reader idles instead of guessing.
        (tmp_path / "card0" / "device" / "gt" / "gt0").mkdir(parents=True)
        monkeypatch.setattr(gpu, "FREQ_GLOB", str(tmp_path / "card*/device/tile*/gt*/freq0"))
        assert gpu.discover_domains() == []

    @pytest.mark.parametrize(
        "key, value, expected",
        [
            ("act_freq_mhz", 1550, "act_freq_mhz=1550"),
            ("driver_freq_mhz", 2000, "driver_freq_mhz=2000"),
            ("throttled", 1, "throttled=1i"),
            ("throttle_thermal", 0, "throttle_thermal=0i"),
        ],
    )
    def test_fmt_field(self, gpu, key, value, expected):
        assert gpu._fmt_field(key, value) == expected
